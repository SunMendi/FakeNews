from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ('id', 'email', 'username', 'is_staff', 'is_active', 'is_journalist_verified')
    search_fields = ('email', 'username', 'google_sub')
    fieldsets = UserAdmin.fieldsets + (
        ('Google', {'fields': ('google_sub', 'avatar_url')}),
        ('Verification', {'fields': ('is_journalist_verified',)}),
    )
