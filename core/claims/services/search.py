from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import hashlib
from typing import Iterable

from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
from django.db import connection
from pgvector.django import CosineDistance

from claims.services.embeddings import embed_text
from news_sources.models import ArticlePassage


@dataclass(frozen=True)
class RankedPassage:
    passage: ArticlePassage
    score: float
    retrieval_method: str


@dataclass(frozen=True)
class ArticleEvidence:
    article_id: int
    title: str
    url: str
    published_at: object
    snippets: tuple[str, ...]


def normalize_query(text: str) -> str:
    return " ".join(text.strip().split()).lower()


def _bounded_limit(value: int, default: int, max_limit: int) -> int:
    if value <= 0:
        return default
    return min(value, max_limit)


def query_variants(raw_query: str) -> list[str]:
    normalized = normalize_query(raw_query)
    variants: list[str] = []
    for candidate in [raw_query.strip(), normalized]:
        compact = " ".join(candidate.split())
        if compact and compact not in variants:
            variants.append(compact)
    return variants


BENGALI_STOPWORDS = {
    "ও", "এবং", "থেকে", "হলো", "ছিল", "হয়ে", "করা", "করে", "এর", "কি", "নাকি", "একটু", "বলো", "তো", "একটি", "জন্য"
}

def _clean_bengali_query(query: str) -> str:
    tokens = query.split()
    cleaned = [t for t in tokens if t not in BENGALI_STOPWORDS]
    return " ".join(cleaned) if cleaned else query

def lexical_passage_search(query_text: str, limit: int = 30) -> list[ArticlePassage]:
    if not query_text.strip():
        return []

    # Clean the query of common noise words to improve precision
    cleaned_query = _clean_bengali_query(query_text)

    if connection.vendor != "postgresql":
        return list(
            ArticlePassage.objects.filter(text__icontains=cleaned_query)
            .select_related("article")
            .order_by("-article__published_at", "-id")[:limit]
        )

    # Use 'websearch' for more natural AND/OR ranking logic
    # Use 'simple' config as it is safest for Bengali without a dedicated dictionary
    search_vector = SearchVector("text", config="simple")
    search_query = SearchQuery(cleaned_query, config="simple", search_type="websearch")
    
    queryset = (
        ArticlePassage.objects.annotate(rank=SearchRank(search_vector, search_query))
        .filter(rank__gt=0.01) # Minimum rank threshold to filter out low-quality matches
        .select_related("article")
        .order_by("-rank", "-article__published_at", "-id")
    )
    return list(queryset[:limit])


def vector_passage_search(query_embedding: list[float], limit: int = 30) -> list[ArticlePassage]:
    return list(
        ArticlePassage.objects.filter(embedding__isnull=False)
        .select_related("article")
        .annotate(distance=CosineDistance("embedding", query_embedding))
        .order_by("distance", "-article__published_at", "-id")[:limit]
    )


def reciprocal_rank_fusion(
    ranked_lists: Iterable[list[object]],
    weights: list[float] | None = None,
    limit: int = 20,
    rrf_k: int = 60,
) -> list[RankedPassage]:
    """
    Combine multiple ranked lists using Weighted Reciprocal Rank Fusion (RRF).
    'weights' allows prioritizing certain methods (e.g., Lexical > Vector).
    """
    passage_by_id: dict[int, ArticlePassage] = {}
    method_by_id: dict[int, set[str]] = defaultdict(set)
    fused_scores: dict[int, float] = defaultdict(float)

    # Convert Iterable to list to safely zip with weights
    lists = list(ranked_lists)
    if weights is None:
        weights = [1.0] * len(lists)
    
    if len(weights) != len(lists):
        raise ValueError("Number of weights must match number of ranked lists")

    for method_index, (ranked_list, weight) in enumerate(zip(lists, weights), start=1):
        method_name = f"method_{method_index}"
        for rank, entry in enumerate(ranked_list, start=1):
            passage = getattr(entry, "passage", entry)
            passage_by_id[passage.id] = passage
            method_by_id[passage.id].add(method_name)
            # Apply the weight to the RRF score
            fused_scores[passage.id] += weight * (1.0 / (rrf_k + rank))

    ranked_ids = sorted(fused_scores.items(), key=lambda item: item[1], reverse=True)
    return [
        RankedPassage(
            passage=passage_by_id[passage_id],
            score=score,
            retrieval_method="+".join(sorted(method_by_id[passage_id])),
        )
        for passage_id, score in ranked_ids[:limit]
    ]


def hybrid_passage_search(
    raw_query: str,
    final_limit: int = 8,
    per_method_limit: int = 20,
    per_article_limit: int = 2,
) -> list[RankedPassage]:
    """
    Perform a hybrid search using Lexical (Weighted 2.0) and Vector (Weighted 1.0) methods.
    Returns fused results capped per article to ensure source diversity.
    """
    safe_final_limit = _bounded_limit(final_limit, default=8, max_limit=30)
    safe_per_method_limit = _bounded_limit(per_method_limit, default=20, max_limit=100)
    safe_per_article_limit = _bounded_limit(per_article_limit, default=2, max_limit=5)

    variants = query_variants(raw_query)
    if not variants:
        return []

    lexical_results: list[ArticlePassage] = []
    for variant in variants:
        lexical_results.extend(lexical_passage_search(variant, limit=safe_per_method_limit))

    vector_results: list[ArticlePassage] = []
    try:
        vector_results = vector_passage_search(
            embed_text(variants[0]),
            limit=safe_per_method_limit,
        )
    except Exception:
        # Graceful fallback if embedding service is down
        vector_results = []

    # DEDUPE lists before fusion to ensure rank stability
    fused = reciprocal_rank_fusion(
        ranked_lists=[_dedupe_passages(lexical_results), _dedupe_passages(vector_results)],
        weights=[2.0, 1.0], # Prioritize Lexical (Exact Entity Matches)
        limit=safe_per_method_limit * 2,
    )
    return _cap_passages_per_article(fused, safe_final_limit, safe_per_article_limit)


def assemble_article_evidence(ranked_passages: list[RankedPassage]) -> list[ArticleEvidence]:
    evidence_by_article: dict[int, ArticleEvidence] = {}

    for ranked in ranked_passages:
        article = ranked.passage.article
        snippet = build_evidence_snippet(ranked.passage.text)
        existing = evidence_by_article.get(article.id)
        if existing is None:
            evidence_by_article[article.id] = ArticleEvidence(
                article_id=article.id,
                title=article.title,
                url=article.url,
                published_at=article.published_at,
                snippets=(snippet,),
            )
            continue

        if snippet not in existing.snippets:
            evidence_by_article[article.id] = ArticleEvidence(
                article_id=existing.article_id,
                title=existing.title,
                url=existing.url,
                published_at=existing.published_at,
                snippets=existing.snippets + (snippet,),
            )

    return list(evidence_by_article.values())


def build_evidence_snapshot_hash(ranked_passages: list[RankedPassage]) -> str:
    parts = [f"{item.passage.id}:{round(item.score, 6)}" for item in ranked_passages]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def build_evidence_snippet(text: str, limit: int = 240) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


def _dedupe_passages(passages: list[ArticlePassage]) -> list[ArticlePassage]:
    deduped: list[ArticlePassage] = []
    seen_ids: set[int] = set()
    for passage in passages:
        if passage.id in seen_ids:
            continue
        seen_ids.add(passage.id)
        deduped.append(passage)
    return deduped


def _cap_passages_per_article(
    ranked_passages: list[RankedPassage],
    final_limit: int,
    per_article_limit: int,
) -> list[RankedPassage]:
    selected: list[RankedPassage] = []
    counts: dict[int, int] = defaultdict(int)

    for ranked in ranked_passages:
        article_id = ranked.passage.article_id
        if counts[article_id] >= per_article_limit:
            continue
        counts[article_id] += 1
        selected.append(ranked)
        if len(selected) >= final_limit:
            break

    return selected
