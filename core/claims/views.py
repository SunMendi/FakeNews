from django.db import transaction
import logging
from time import perf_counter
from django.db.models import Count, Max, Q
from django.shortcuts import get_object_or_404
from rest_framework.pagination import LimitOffsetPagination
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from core.utils.permissions import SearchRateLimitPermission
from claims.models import Claim, ClaimAnswer, ClaimVote
from claims.permissions import IsStaffUser
from claims.serializers import (
    ClaimAnswerCreateSerializer,
    ClaimAnswerResponseSerializer,
    ClaimFeedItemSerializer,
    ClaimModerationSerializer,
    ClaimVoteSerializer,
    SearchRequestSerializer,
    SearchResponseSerializer,
)
from claims.services.embeddings import embed_text
from claims.services.search import (
    build_evidence_snippet,
    build_evidence_snapshot_hash,
    hybrid_passage_search,
    normalize_query,
)
from claims.services.verdict import build_verdict
from news_sources.models import Article

logger = logging.getLogger(__name__)


def _log_retrieval_results(claim_id: int, query: str, ranked_passages):
    logger.info(
        "retrieval_results claim_id=%s query=%r count=%s passages=%s",
        claim_id,
        query,
        len(ranked_passages),
        [
            {
                "passage_id": ranked.passage.id,
                "article_id": ranked.passage.article_id,
                "title": ranked.passage.article.title,
                "score": round(ranked.score, 6),
                "method": ranked.retrieval_method,
                "snippet": build_evidence_snippet(ranked.passage.text, limit=160),
            }
            for ranked in ranked_passages
        ],
    )


def _get_actor_user(request):
    """
    Temporary helper for local testing:
    If auth is disabled and request has no user, use/create a demo user.
    """
    if getattr(request, "user", None) and request.user.is_authenticated:
        return request.user

    demo_user, _ = User.objects.get_or_create(
        username="local_tester",
        defaults={
            "email": "local_tester@example.com",
        },
    )
    return demo_user


class SearchAPIView(APIView):
    # permission_classes = [IsAuthenticated]
    permission_classes = [AllowAny, SearchRateLimitPermission]

    def post(self, request):
        started_at = perf_counter()
        serializer = SearchRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        actor_user = _get_actor_user(request)
        raw_query = serializer.validated_data["query"]
        final_limit = serializer.validated_data["final_limit"]
        per_method_limit = serializer.validated_data["per_method_limit"]

        normalized_query = normalize_query(raw_query)
        retrieval_query = raw_query.strip() or normalized_query
        latest_corpus_updated_at = Article.objects.aggregate(
            latest=Max("fetched_at")
        )["latest"]

        with transaction.atomic():
            claim = (
                Claim.objects.select_for_update()
                .filter(created_by=actor_user, normalized_query=normalized_query)
                .first()
            )

            # ARCHITECTURAL FIX: Check if we already have a SUCCESSFUL cached AI verdict.
            # We only skip the LLM if we have a verdict AND confidence > 0.
            # If confidence is 0, it likely means a previous AI attempt failed.
            if (
                claim 
                and claim.verdict 
                and claim.confidence_percent > 0 
                and claim.verification_corpus_updated_at == latest_corpus_updated_at
            ):
                ranked_passages = hybrid_passage_search(
                    raw_query=retrieval_query,
                    final_limit=final_limit,
                    per_method_limit=per_method_limit,
                )
                _log_retrieval_results(claim.id, retrieval_query, ranked_passages)
                logger.info("cache_hit claim_id=%s query=%r", claim.id, normalized_query)
                payload = {
                    "claim_id": claim.id,
                    "claim_status": claim.status,
                    "normalized_query": normalized_query,
                    "verdict": claim.verdict,
                    "confidence_percent": claim.confidence_percent,
                    "explanation": claim.explanation,
                    "sources": claim.verified_sources or [],
                }
                response_serializer = SearchResponseSerializer(data=payload)
                response_serializer.is_valid(raise_exception=True)
                return Response(response_serializer.data, status=status.HTTP_200_OK)

            if claim is None:
                claim = Claim(
                    created_by=actor_user,
                    original_query=raw_query.strip(),
                    normalized_query=normalized_query,
                )
                try:
                    claim.embedding = embed_text(normalized_query)
                except Exception:
                    claim.embedding = None
                claim.save()

        ranked_passages = hybrid_passage_search(
            raw_query=retrieval_query,
            final_limit=final_limit,
            per_method_limit=per_method_limit,
        )
        _log_retrieval_results(claim.id, retrieval_query, ranked_passages)
        evidence_snapshot_hash = build_evidence_snapshot_hash(ranked_passages)

        verdict_result = build_verdict(raw_query.strip(), ranked_passages)
        claim.verdict = verdict_result.verdict
        claim.confidence_percent = verdict_result.confidence_percent
        claim.explanation = verdict_result.explanation
        claim.verified_sources = verdict_result.verified_sources
        claim.evidence_snapshot_hash = evidence_snapshot_hash
        claim.verification_corpus_updated_at = latest_corpus_updated_at
        claim.save(
            update_fields=[
                "verdict",
                "confidence_percent",
                "explanation",
                "verified_sources",
                "evidence_snapshot_hash",
                "verification_corpus_updated_at",
            ]
        )

        payload = {
            "claim_id": claim.id,
            "claim_status": claim.status,
            "normalized_query": normalized_query,
            "verdict": verdict_result.verdict,
            "confidence_percent": verdict_result.confidence_percent,
            "explanation": verdict_result.explanation,
            "sources": verdict_result.verified_sources,
        }
        response_serializer = SearchResponseSerializer(data=payload)
        response_serializer.is_valid(raise_exception=True)
        duration_ms = int((perf_counter() - started_at) * 1000)
        logger.info(
            "search_completed user_id=%s claim_id=%s normalized_query=%r results=%s duration_ms=%s",
            actor_user.id,
            claim.id,
            normalized_query,
            len(verdict_result.verified_sources),
            duration_ms,
        )
        return Response(response_serializer.data, status=status.HTTP_200_OK)


class ClaimsFeedAPIView(APIView):
    # permission_classes = [IsAuthenticated]
    permission_classes = [AllowAny]
    pagination_class = LimitOffsetPagination

    def get(self, request):
        queryset = (
            Claim.objects.select_related("created_by")
            .annotate(
                answers_count=Count("answers", distinct=True),
                upvotes=Count("votes", filter=Q(votes__value=1), distinct=True),
                downvotes=Count("votes", filter=Q(votes__value=-1), distinct=True),
            )
            .order_by("-created_at")
        )

        paginator = self.pagination_class()
        paginated = paginator.paginate_queryset(queryset, request)
        serializer = ClaimFeedItemSerializer(paginated, many=True)
        return paginator.get_paginated_response(serializer.data)


class ClaimAnswerAPIView(APIView):
    # permission_classes = [IsAuthenticated]
    permission_classes = [AllowAny]

    def get(self, request, claim_id: int):
        claim = get_object_or_404(Claim, pk=claim_id)
        answers = claim.answers.select_related("created_by").all()
        serializer = ClaimAnswerResponseSerializer(answers, many=True)
        return Response(
            {
                "claim_id": claim.id,
                "answers": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    def post(self, request, claim_id: int):
        actor_user = _get_actor_user(request)
        claim = get_object_or_404(Claim, pk=claim_id)
        serializer = ClaimAnswerCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        answer = ClaimAnswer.objects.create(
            claim=claim,
            created_by=actor_user,
            body=serializer.validated_data["body"],
            evidence_url=serializer.validated_data.get("evidence_url", ""),
        )

        response_serializer = ClaimAnswerResponseSerializer(answer)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class ClaimVoteAPIView(APIView):
    # permission_classes = [IsAuthenticated]
    permission_classes = [AllowAny]

    def post(self, request, claim_id: int):
        actor_user = _get_actor_user(request)
        claim = get_object_or_404(Claim, pk=claim_id)
        serializer = ClaimVoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        vote, _ = ClaimVote.objects.update_or_create(
            claim=claim,
            created_by=actor_user,
            defaults={"value": serializer.validated_data["value"]},
        )

        upvotes = ClaimVote.objects.filter(claim=claim, value=1).count()
        downvotes = ClaimVote.objects.filter(claim=claim, value=-1).count()

        return Response(
            {
                "claim_id": claim.id,
                "your_vote": "upvote" if vote.value == 1 else "downvote",
                "upvotes": upvotes,
                "downvotes": downvotes,
            },
            status=status.HTTP_200_OK,
        )


class ClaimModerationAPIView(APIView):
    permission_classes = [IsStaffUser]

    def patch(self, request, claim_id: int):
        claim = get_object_or_404(Claim, pk=claim_id)
        serializer = ClaimModerationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        claim.status = serializer.validated_data["status"]
        claim.save(update_fields=["status", "updated_at"])
        return Response(
            {
                "claim_id": claim.id,
                "status": claim.status,
                "updated_at": claim.updated_at,
            },
            status=status.HTTP_200_OK,
        )
