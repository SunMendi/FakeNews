import json
import secrets
import urllib.parse
import urllib.request

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import transaction
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken


User = get_user_model()

#creates a unique username from email 
def _generate_username(email: str) -> str:
    base = email.split('@')[0].strip().lower().replace(' ', '') or 'user'
    candidate = base[:150]
    suffix = 1
    while User.objects.filter(username=candidate).exists():
        suffix += 1
        candidate = f"{base[:140]}{suffix}"
    return candidate


def _post_form(url: str, payload: dict) -> dict:
    data = urllib.parse.urlencode(payload).encode('utf-8')
    http_request = urllib.request.Request(url=url, data=data, method='POST')
    http_request.add_header('Content-Type', 'application/x-www-form-urlencoded')
    with urllib.request.urlopen(http_request, timeout=15) as response:
        return json.loads(response.read().decode('utf-8'))


def _get_json(url: str, params: dict) -> dict:
    query = urllib.parse.urlencode(params)
    with urllib.request.urlopen(f"{url}?{query}", timeout=15) as response:
        return json.loads(response.read().decode('utf-8'))


class GoogleLoginURLView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        state = secrets.token_urlsafe(16)
        params = {
            'client_id': settings.GOOGLE_CLIENT_ID,
            'redirect_uri': settings.GOOGLE_REDIRECT_URI,
            'response_type': 'code',
            'scope': 'openid email profile',
            'access_type': 'offline',
            'prompt': 'consent',
            'state': state,
        }
        auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(params)}"
        return Response({'auth_url': auth_url, 'state': state})


class GoogleCallbackView(APIView):
    permission_classes = [AllowAny]

    def _handle_callback(self, request):
        if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET or not settings.GOOGLE_REDIRECT_URI:
            return Response(
                {'detail': 'Google OAuth settings are missing'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )  

        body = request.data if hasattr(request, 'data') and isinstance(request.data, dict) else {}
        code = request.query_params.get('code') or body.get('code')
        if not code:
            return Response({'detail': 'Missing code'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            token_data = _post_form(
                'https://oauth2.googleapis.com/token',
                {
                    'code': code,
                    'client_id': settings.GOOGLE_CLIENT_ID,
                    'client_secret': settings.GOOGLE_CLIENT_SECRET,
                    'redirect_uri': settings.GOOGLE_REDIRECT_URI,
                    'grant_type': 'authorization_code',
                },
            )
            access_token = token_data.get('access_token')
            if not access_token:
                return Response({'detail': 'Failed to get access token'}, status=status.HTTP_400_BAD_REQUEST)

            profile = _get_json(
                'https://www.googleapis.com/oauth2/v3/userinfo',
                {'access_token': access_token},
            )
        except Exception:
            return Response({'detail': 'Google authentication failed'}, status=status.HTTP_400_BAD_REQUEST)

        google_sub = profile.get('sub')
        email = profile.get('email')
        email_verified = profile.get('email_verified')

        if not google_sub or not email or not email_verified:
            return Response({'detail': 'Google account data is invalid'}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            user = User.objects.filter(google_sub=google_sub).first()
            if not user:
                user = User.objects.filter(email=email).first()

            if not user:
                user = User.objects.create(
                    email=email,
                    username=_generate_username(email),
                    google_sub=google_sub,
                    avatar_url=profile.get('picture', ''),
                    first_name=profile.get('given_name', ''),
                    last_name=profile.get('family_name', ''),
                )
                user.set_unusable_password()
                user.save(update_fields=['password'])
            else:
                changed_fields = []
                if not user.google_sub:
                    user.google_sub = google_sub
                    changed_fields.append('google_sub')
                picture = profile.get('picture', '')
                if picture and user.avatar_url != picture:
                    user.avatar_url = picture
                    changed_fields.append('avatar_url')
                if changed_fields:
                    user.save(update_fields=changed_fields)

            default_group, _ = Group.objects.get_or_create(name='user')
            user.groups.add(default_group)

        refresh = RefreshToken.for_user(user)
        return Response(
            {
                'access': str(refresh.access_token),
                'refresh': str(refresh),
                'user': {
                    'id': user.id,
                    'email': user.email,
                    'username': user.username,
                    'is_journalist_verified': user.is_journalist_verified,
                    'groups': list(user.groups.values_list('name', flat=True)),
                },
            },
            status=status.HTTP_200_OK,
        )

    def get(self, request):
        return self._handle_callback(request)

    def post(self, request):
        return self._handle_callback(request)
