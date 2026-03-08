from __future__ import annotations

import re
from dataclasses import dataclass

from claims.services.embeddings import embed_text
from news_sources.models import Article, ArticlePassage


TARGET_WORDS_PER_PASSAGE = 200
PASSAGE_OVERLAP_WORDS = 40
MIN_WORDS_PER_PASSAGE = 40


@dataclass(frozen=True)
class PassageChunk:
    position: int
    text: str


def build_article_text(title: str, content: str) -> str:
    title = (title or "").strip()
    content = (content or "").strip()
    return f"{title}\n\n{content}".strip()


def split_article_into_passages(title: str, content: str) -> list[PassageChunk]:
    article_text = build_article_text(title, content)
    if not article_text:
        return []

    words = article_text.split()
    if not words:
        return []

    step = max(1, TARGET_WORDS_PER_PASSAGE - PASSAGE_OVERLAP_WORDS)
    chunks: list[PassageChunk] = []
    position = 0

    for start in range(0, len(words), step):
        window = words[start : start + TARGET_WORDS_PER_PASSAGE]
        if not window:
            continue
        if len(window) < MIN_WORDS_PER_PASSAGE and chunks:
            previous = chunks[-1]
            merged_text = f"{previous.text} {' '.join(window)}".strip()
            chunks[-1] = PassageChunk(position=previous.position, text=merged_text)
            break

        passage_text = _normalize_chunk_text(" ".join(window))
        if not passage_text:
            continue
        chunks.append(PassageChunk(position=position, text=passage_text))
        position += 1

        if start + TARGET_WORDS_PER_PASSAGE >= len(words):
            break

    return chunks


def refresh_article_passages(article: Article) -> int:
    chunks = split_article_into_passages(article.title, article.content)
    article.passages.all().delete()

    passage_objects: list[ArticlePassage] = []
    for chunk in chunks:
        embedding = None
        try:
            embedding = embed_text(chunk.text)
        except Exception:
            embedding = None

        passage_objects.append(
            ArticlePassage(
                article=article,
                position=chunk.position,
                text=chunk.text,
                embedding=embedding,
                char_count=len(chunk.text),
            )
        )

    if passage_objects:
        ArticlePassage.objects.bulk_create(passage_objects)
    return len(passage_objects)


def _normalize_chunk_text(text: str) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    return compact
