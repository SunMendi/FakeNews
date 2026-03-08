from django.db import models
from django.conf import settings
from pgvector.django import VectorField


class ClaimStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    VERIFIED = "verified", "Verified"
    REJECTED = "rejected", "Rejected"


class Claim(models.Model):
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="claims",
    )
    original_query = models.TextField()
    normalized_query = models.TextField()
    embedding = VectorField(dimensions=384, null=True, blank=True)
    
    # --- New Persistence Fields ---
    verdict = models.CharField(
        max_length=20, 
        choices=[("true", "True"), ("false", "False"), ("uncertain", "Uncertain")],
        null=True, blank=True
    )
    confidence_percent = models.IntegerField(default=0)
    explanation = models.TextField(null=True, blank=True)
    verified_sources = models.JSONField(default=list, blank=True)
    evidence_snapshot_hash = models.CharField(max_length=64, null=True, blank=True)
    verification_corpus_updated_at = models.DateTimeField(null=True, blank=True)
    # ------------------------------

    status = models.CharField(
        max_length=20,
        choices=ClaimStatus.choices,
        default=ClaimStatus.PENDING,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["created_by", "normalized_query"],
                name="unique_claim_per_user_normalized_query",
            )
        ]
        indexes = [
            models.Index(fields=["status", "-created_at"], name="claim_status_created_idx"),
            models.Index(fields=["-created_at"], name="claim_created_idx"),
        ]

    def __str__(self):
        return f"Claim {self.id}: {self.original_query[:50]}"


class ClaimAnswer(models.Model):
    claim = models.ForeignKey(
        Claim,
        on_delete=models.CASCADE,
        related_name="answers",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="claim_answers",
    )
    body = models.TextField()
    evidence_url = models.URLField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Answer {self.id} for Claim {self.claim_id}"


class ClaimVoteValue(models.IntegerChoices):
    DOWNVOTE = -1, "Downvote"
    UPVOTE = 1, "Upvote"


class ClaimVote(models.Model):
    claim = models.ForeignKey(
        Claim,
        on_delete=models.CASCADE,
        related_name="votes",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="claim_votes",
    )
    value = models.SmallIntegerField(choices=ClaimVoteValue.choices)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["claim", "created_by"],
                name="unique_vote_per_user_per_claim",
            )
        ]

    def __str__(self):
        return f"Vote {self.id} on Claim {self.claim_id}"
