from django.contrib import admin
from .models import NewsSource, Article

@admin.register(NewsSource)
class NewsSourceAdmin(admin.ModelAdmin):
    list_display = ('name', 'rss_url', 'trust_weight', 'created_at')
    search_fields = ('name', 'rss_url')

@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ('title', 'source', 'published_at', 'fetched_at')
    list_filter = ('source', 'published_at')
    search_fields = ('title', 'content')
