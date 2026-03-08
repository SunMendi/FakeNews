from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVector
from django.db import models
from pgvector.django import VectorField
from pgvector.django import HnswIndex

class NewsSource(models.Model):
    """The 'Address Book' - your trusted newspapers"""
    name = models.CharField(max_length=100)
    rss_url = models.URLField(unique=True)
    # Default trust weight (e.g., 90 out of 100)
    trust_weight = models.IntegerField(default=90)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class Article(models.Model):
    """The 'Letters' - the actual news stories we scrape"""
    source = models.ForeignKey(NewsSource, on_delete=models.CASCADE, related_name='articles')
    title = models.CharField(max_length=500)
    content = models.TextField() # This will store the "Clean Text"
    summary = models.TextField(null=True, blank=True) # AI-generated contextual summary
    url = models.URLField(max_length=1000, unique=True) # To avoid saving the same link twice
    embedding = VectorField(dimensions=384, null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            GinIndex(
                fields=["title"],
                name="article_title_trgm_idx",
                opclasses=["gin_trgm_ops"],
            ),
            GinIndex(
                fields=["content"],
                name="article_content_trgm_idx",
                opclasses=["gin_trgm_ops"],
            ),
            HnswIndex(
                fields=["embedding"],
                name="article_embedding_hnsw_idx",
                opclasses=["vector_cosine_ops"],
                m=16,
                ef_construction=64,
            ),
        ]

    def __str__(self):
        return self.title


class ArticlePassage(models.Model):
    article = models.ForeignKey(
        Article,
        on_delete=models.CASCADE,
        related_name="passages",
    )
    position = models.PositiveIntegerField()
    text = models.TextField()
    embedding = VectorField(dimensions=384, null=True, blank=True)
    char_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["article", "position"],
                name="unique_article_passage_position",
            ),
        ]
        indexes = [
            GinIndex(
                SearchVector("text", config="simple"),
                name="article_passage_fts_idx",
            ),
            HnswIndex(
                fields=["embedding"],
                name="art_passage_embed_hnsw_idx",
                opclasses=["vector_cosine_ops"],
                m=16,
                ef_construction=64,
            ),
            models.Index(fields=["article", "position"], name="article_passage_order_idx"),
        ]
        ordering = ["article_id", "position", "id"]

    def __str__(self):
        return f"Passage {self.id} for article {self.article_id}"
