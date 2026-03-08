from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import User
from claims.models import Claim
from claims.services.search import (
    RankedPassage,
    build_evidence_snapshot_hash,
    normalize_query,
    reciprocal_rank_fusion,
)
from news_sources.models import Article, NewsSource
from news_sources.services import refresh_article_passages


class SearchHelpersTest(SimpleTestCase):
    def test_normalize_query_collapses_spaces_and_lowercases(self):
        self.assertEqual(normalize_query("  HeLLo   Bangla  "), "hello bangla")

    def test_reciprocal_rank_fusion_merges_and_orders_results(self):
        passage_1 = SimpleNamespace(id=1)
        passage_2 = SimpleNamespace(id=2)
        passage_3 = SimpleNamespace(id=3)

        fused = reciprocal_rank_fusion(
            ranked_lists=[
                [passage_1, passage_2],
                [passage_2, passage_3],
            ],
            limit=3,
        )

        self.assertEqual(fused[0].passage.id, 2)
        self.assertEqual(len(fused), 3)

    def test_evidence_snapshot_hash_changes_with_ranked_passages(self):
        article = SimpleNamespace(id=10)
        passage_1 = SimpleNamespace(id=1, article=article, article_id=10)
        passage_2 = SimpleNamespace(id=2, article=article, article_id=10)

        first = build_evidence_snapshot_hash(
            [
                RankedPassage(passage=passage_1, score=0.9, retrieval_method="method_1"),
                RankedPassage(passage=passage_2, score=0.7, retrieval_method="method_2"),
            ]
        )
        second = build_evidence_snapshot_hash(
            [
                RankedPassage(passage=passage_1, score=0.9, retrieval_method="method_1"),
            ]
        )

        self.assertNotEqual(first, second)


class SearchAPITest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="mehedi",
            email="mehedi@example.com",
            password="StrongPass123!",
        )
        self.source = NewsSource.objects.create(
            name="Daily Test",
            rss_url="https://example.com/rss",
            trust_weight=90,
        )
        self.article = Article.objects.create(
            source=self.source,
            title="Bangla fake news example",
            content=(
                "Bangla News investigators said the claim was false after reviewing official records. "
                "The evidence passage clearly contradicts the rumor and gives the exact location."
            ),
            url="https://example.com/article/1",
            published_at=timezone.now(),
            embedding=[0.1] * 384,
        )
        refresh_article_passages(self.article)
        self.url = reverse("search")

    def test_search_rejects_blank_query(self):
        response = self.client.post(self.url, {"query": "   "}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("query", response.data)

    @patch(
        "claims.services.verdict.llm.generate",
        return_value='{"verdict":"false","confidence_percent":84,"explanation":"Passages contradict the claim.","passage_evaluations":[{"passage_id":1,"label":"contradict","reason":"Official records refute it."}]}',
    )
    @patch("claims.views.embed_text", return_value=[0.2] * 384)
    @patch("claims.services.search.embed_text", return_value=[0.2] * 384)
    def test_search_returns_verdict_and_sources(self, _search_embed_mock, _claim_embed_mock, _judge_mock):
        response = self.client.post(self.url, {"query": "Bangla News"}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertIn("claim_id", response.data)
        self.assertEqual(response.data["normalized_query"], "bangla news")
        self.assertEqual(response.data["claim_status"], "pending")
        self.assertEqual(response.data["verdict"], "false")
        self.assertEqual(response.data["confidence_percent"], 84)
        self.assertGreaterEqual(len(response.data["sources"]), 1)
        self.assertEqual(response.data["sources"][0]["title"], self.article.title)
        self.assertIn("evidence_snippets", response.data["sources"][0])
        self.assertGreaterEqual(len(response.data["sources"][0]["evidence_snippets"]), 1)

    @patch(
        "claims.services.verdict.llm.generate",
        return_value='{"verdict":"uncertain","confidence_percent":42,"explanation":"Need more evidence.","passage_evaluations":[{"passage_id":1,"label":"support","reason":"Related passage."}]}',
    )
    @patch("claims.views.embed_text", return_value=[0.2] * 384)
    @patch("claims.services.search.embed_text", return_value=[0.2] * 384)
    def test_search_reuses_existing_claim_for_same_normalized_query(self, _search_embed_mock, _claim_embed_mock, _judge_mock):
        first = self.client.post(self.url, {"query": "Bangla News"}, format="json")
        second = self.client.post(self.url, {"query": "  bangla   news  "}, format="json")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.data["claim_id"], second.data["claim_id"])
        self.assertEqual(first.data["sources"], second.data["sources"])


class ClaimsCommunityAPITest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="user1",
            email="user1@example.com",
            password="StrongPass123!",
        )
        self.other_user = User.objects.create_user(
            username="user2",
            email="user2@example.com",
            password="StrongPass123!",
        )
        self.staff_user = User.objects.create_user(
            username="admin1",
            email="admin1@example.com",
            password="StrongPass123!",
            is_staff=True,
        )
        self.claim = Claim.objects.create(
            created_by=self.user,
            original_query="Is this claim true?",
            normalized_query="is this claim true?",
        )

    def test_claims_feed_returns_claims(self):
        response = self.client.get(reverse("claims-feed"))
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(len(response.data["results"]), 1)

    def test_user_can_submit_answer(self):
        response = self.client.post(
            reverse("claim-answers", kwargs={"claim_id": self.claim.id}),
            {"body": "I found evidence from official source.", "evidence_url": "https://example.com/evidence"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["claim"], self.claim.id)

    def test_user_can_list_answers_for_claim(self):
        self.client.post(
            reverse("claim-answers", kwargs={"claim_id": self.claim.id}),
            {"body": "Evidence line 1", "evidence_url": "https://example.com/evidence-1"},
            format="json",
        )

        response = self.client.get(reverse("claim-answers", kwargs={"claim_id": self.claim.id}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["claim_id"], self.claim.id)
        self.assertEqual(len(response.data["answers"]), 1)
        self.assertEqual(response.data["answers"][0]["body"], "Evidence line 1")

    def test_user_can_vote_and_update_vote(self):
        first = self.client.post(
            reverse("claim-vote", kwargs={"claim_id": self.claim.id}),
            {"vote": "upvote"},
            format="json",
        )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.data["your_vote"], "upvote")
        self.assertEqual(first.data["upvotes"], 1)

        second = self.client.post(
            reverse("claim-vote", kwargs={"claim_id": self.claim.id}),
            {"vote": "downvote"},
            format="json",
        )
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.data["your_vote"], "downvote")
        self.assertEqual(second.data["downvotes"], 1)

    def test_non_staff_user_cannot_moderate_claim(self):
        self.client.force_authenticate(user=self.other_user)
        response = self.client.patch(
            reverse("claim-moderate", kwargs={"claim_id": self.claim.id}),
            {"status": "verified"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_staff_user_can_moderate_claim(self):
        self.client.force_authenticate(user=self.staff_user)
        response = self.client.patch(
            reverse("claim-moderate", kwargs={"claim_id": self.claim.id}),
            {"status": "verified"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, "verified")
