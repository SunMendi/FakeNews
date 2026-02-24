from django.urls import path

from .views import GoogleCallbackView, GoogleLoginURLView


urlpatterns = [
    path('google/login-url/', GoogleLoginURLView.as_view(), name='google-login-url'),
    path('google/callback/', GoogleCallbackView.as_view(), name='google-callback'),
]
