from django.urls import path

from claims.views import ClaimAnswerAPIView, ClaimModerationAPIView, ClaimVoteAPIView, ClaimsFeedAPIView, SearchAPIView


urlpatterns = [
    path("search/", SearchAPIView.as_view(), name="search"),
    path("claims/feed/", ClaimsFeedAPIView.as_view(), name="claims-feed"),
    path("claims/<int:claim_id>/answers/", ClaimAnswerAPIView.as_view(), name="claim-answers"),
    path("claims/<int:claim_id>/votes/", ClaimVoteAPIView.as_view(), name="claim-vote"),
    path("claims/<int:claim_id>/moderate/", ClaimModerationAPIView.as_view(), name="claim-moderate"),
]
