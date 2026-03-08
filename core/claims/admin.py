from django.contrib import admin

from claims.models import Claim, ClaimAnswer, ClaimVote


@admin.register(Claim)
class ClaimAdmin(admin.ModelAdmin):
    list_display = ("id", "created_by", "status", "created_at")
    search_fields = ("original_query", "normalized_query", "created_by__username")
    list_filter = ("status", "created_at")


@admin.register(ClaimAnswer)
class ClaimAnswerAdmin(admin.ModelAdmin):
    list_display = ("id", "claim", "created_by", "created_at")
    search_fields = ("body", "created_by__username")
    list_filter = ("created_at",)


@admin.register(ClaimVote)
class ClaimVoteAdmin(admin.ModelAdmin):
    list_display = ("id", "claim", "created_by", "value", "created_at")
    list_filter = ("value", "created_at")
