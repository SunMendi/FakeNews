from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    email = models.EmailField(unique=True)
    google_sub = models.CharField(max_length=255, unique=True, null=True, blank=True)
    avatar_url = models.URLField(blank=True)
    is_journalist_verified = models.BooleanField(default=False)

    def __str__(self):
        return self.email
