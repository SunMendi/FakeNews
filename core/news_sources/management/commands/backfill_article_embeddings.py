from django.core.management.base import BaseCommand

from claims.services.embeddings import embed_text
from news_sources.models import Article
from news_sources.services import build_article_text, refresh_article_passages


class Command(BaseCommand):
    help = "Generate embeddings for existing articles that do not have one yet."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=100,
            help="Maximum number of articles to process in one run.",
        )

    def handle(self, *args, **options):
        limit = max(1, options["limit"])
        queryset = Article.objects.filter(embedding__isnull=True).order_by("-published_at", "-id")[:limit]

        processed = 0
        skipped = 0

        for article in queryset:
            article_text = build_article_text(article.title, article.content)
            if not article_text:
                skipped += 1
                continue

            try:
                article.embedding = embed_text(article_text)
                article.save(update_fields=["embedding"])
                refresh_article_passages(article)
                processed += 1
                self.stdout.write(self.style.SUCCESS(f"Embedded article {article.id}: {article.title[:60]}"))
            except Exception as exc:
                self.stdout.write(self.style.WARNING(f"Failed article {article.id}: {exc}"))

        self.stdout.write(
            self.style.SUCCESS(
                f"Backfill complete. embedded={processed} skipped={skipped} limit={limit}"
            )
        )
