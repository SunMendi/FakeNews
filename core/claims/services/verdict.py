from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import List

from claims.services.llm import llm
from claims.services.search import (
    RankedPassage,
    assemble_article_evidence,
    build_evidence_snippet,
)


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VerdictResult:
    verdict: str
    confidence_percent: int
    explanation: str
    verified_sources: List[dict]


JUDGE_PROMPT = """
You are an evidence judge for a claim verification system.
You must decide the verdict using only the supplied passages.

Rules:
1. Do not infer missing facts. If a passage does not explicitly support or contradict a key detail, treat it as irrelevant.
2. Be strict about actors, locations, dates, counts, and actions.
3. Prefer "uncertain" when evidence is mixed, incomplete, or only topically related.
4. For each passage, classify it as "support", "contradict", or "irrelevant".
5. Output valid JSON only using this shape:
{
  "verdict": "true" | "false" | "uncertain",
  "confidence_percent": 0-100,
  "explanation": "brief explanation",
  "passage_evaluations": [
    {"passage_id": 1, "label": "support", "reason": "short reason"},
    {"passage_id": 2, "label": "contradict", "reason": "short reason"}
  ]
}
"""


class SemanticJudge:
    def verify_claim(self, query: str, ranked_passages: List[RankedPassage]) -> VerdictResult:
        if not ranked_passages:
            return VerdictResult(
                verdict="uncertain",
                confidence_percent=0,
                explanation="No evidence passages found.",
                verified_sources=[],
            )

        # ARCHITECTURAL FIX: Reduce to Top 4 to stay within Free Tier TPM limits (e.g., Groq)
        top_passages = ranked_passages[:4]
        passages_context = [
            {
                "passage_id": ranked.passage.id,
                "article_id": ranked.passage.article_id,
                "article_title": ranked.passage.article.title,
                # Truncate to 800 chars to avoid "Request too large" errors
                "text": ranked.passage.text[:800], 
            }
            for ranked in top_passages
        ]
        user_prompt = (
            f"User Claim: {query}\n\n"
            f"Evidence Passages:\n{json.dumps(passages_context, ensure_ascii=False)}\n\n"
            "Output JSON:"
        )

        try:
            response_text = llm.generate(
                prompt=user_prompt,
                system_instruction=JUDGE_PROMPT,
                is_json=True,
            )
            if not response_text:
                raise ValueError("Empty response from LLM")

            logger.info(
                "judge_input query=%r passages=%s",
                query,
                [
                    {
                        "passage_id": ranked.passage.id,
                        "article_id": ranked.passage.article_id,
                        "title": ranked.passage.article.title,
                        "snippet": build_evidence_snippet(ranked.passage.text, limit=160),
                    }
                    for ranked in top_passages
                ],
            )
            logger.info("judge_raw_response query=%r response=%s", query, response_text)

            data = json.loads(response_text)
            evaluations = {
                item["passage_id"]: item
                for item in data.get("passage_evaluations", [])
                if "passage_id" in item
            }

            cited_passages = [
                ranked
                for ranked in top_passages
                if evaluations.get(ranked.passage.id, {}).get("label") in {"support", "contradict"}
            ]
            verified_sources = _build_verified_sources(cited_passages)

            return VerdictResult(
                verdict=_coerce_verdict(data.get("verdict")),
                confidence_percent=_coerce_confidence(data.get("confidence_percent")),
                explanation=(data.get("explanation") or "").strip(),
                verified_sources=verified_sources,
            )
        except Exception as exc:
            logger.exception("SemanticJudge failed for query=%r", query)
            return VerdictResult(
                verdict="uncertain",
                confidence_percent=0,
                explanation="AI verification failed. Please try again later.",
                verified_sources=[],
            )


def _build_verified_sources(ranked_passages: list[RankedPassage]) -> list[dict]:
    sources = []
    for evidence in assemble_article_evidence(ranked_passages):
        sources.append(
            {
                "id": evidence.article_id,
                "title": evidence.title,
                "url": evidence.url,
                "published_at": evidence.published_at.isoformat() if evidence.published_at else None,
                "evidence_snippets": list(evidence.snippets),
                "summary": build_evidence_snippet(" ".join(evidence.snippets)),
            }
        )
    return sources


def _coerce_verdict(verdict: str | None) -> str:
    if verdict in {"true", "false", "uncertain"}:
        return verdict
    return "uncertain"


def _coerce_confidence(value: object) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, min(number, 100))


judge = SemanticJudge()


def build_verdict(query: str, ranked_passages: List[RankedPassage]) -> VerdictResult:
    return judge.verify_claim(query, ranked_passages)
