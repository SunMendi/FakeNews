from rest_framework import serializers

from claims.models import ClaimAnswer, ClaimStatus, ClaimVoteValue


class SearchRequestSerializer(serializers.Serializer):
    query = serializers.CharField(max_length=1000, allow_blank=False, trim_whitespace=True)
    final_limit = serializers.IntegerField(required=False, min_value=1, max_value=100, default=20)
    per_method_limit = serializers.IntegerField(required=False, min_value=1, max_value=100, default=30)


class SearchResultArticleSerializer(serializers.Serializer):
    id = serializers.IntegerField(required=False)
    title = serializers.CharField()
    url = serializers.URLField()
    published_at = serializers.DateTimeField(allow_null=True)
    summary = serializers.CharField(allow_blank=True, required=False)
    evidence_snippets = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        default=list,
    )
    source_confidence_percent = serializers.IntegerField(min_value=0, max_value=100, required=False, default=0)


class SearchResponseSerializer(serializers.Serializer):
    claim_id = serializers.IntegerField()
    claim_status = serializers.ChoiceField(choices=ClaimStatus.choices)
    normalized_query = serializers.CharField()
    verdict = serializers.ChoiceField(choices=["true", "false", "uncertain"])
    confidence_percent = serializers.IntegerField(min_value=0, max_value=100)
    explanation = serializers.CharField(allow_blank=True, required=False)
    sources = SearchResultArticleSerializer(many=True)


class ClaimFeedItemSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    query = serializers.CharField(source="original_query")
    status = serializers.ChoiceField(choices=ClaimStatus.choices)
    created_at = serializers.DateTimeField()
    created_by = serializers.CharField(source="created_by.username")
    answers_count = serializers.IntegerField()
    upvotes = serializers.IntegerField()
    downvotes = serializers.IntegerField()


class ClaimAnswerCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClaimAnswer
        fields = ["body", "evidence_url"]

    def validate_body(self, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise serializers.ValidationError("Answer body cannot be blank.")
        if len(cleaned) > 5000:
            raise serializers.ValidationError("Answer body is too long.")
        return cleaned


class ClaimAnswerResponseSerializer(serializers.ModelSerializer):
    created_by = serializers.CharField(source="created_by.username")

    class Meta:
        model = ClaimAnswer
        fields = ["id", "claim", "created_by", "body", "evidence_url", "created_at"]


class ClaimVoteSerializer(serializers.Serializer):
    vote = serializers.ChoiceField(choices=["upvote", "downvote"])

    def to_internal_value(self, data):
        internal = super().to_internal_value(data)
        vote_map = {
            "upvote": ClaimVoteValue.UPVOTE,
            "downvote": ClaimVoteValue.DOWNVOTE,
        }
        internal["value"] = vote_map[internal["vote"]]
        return internal


class ClaimModerationSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=ClaimStatus.choices)
