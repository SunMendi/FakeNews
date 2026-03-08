from django.core.management.base import BaseCommand

from news_sources.models import Article
from news_sources.services import refresh_article_passages


class Command(BaseCommand):
    help = "Generate passages and passage embeddings for existing articles."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=100,
            help="Maximum number of articles to process in one run.",
        )
        parser.add_argument(
            "--only-missing",
            action="store_true",
            help="Only process articles that do not have any passages yet.",
        )

    def handle(self, *args, **options):
        limit = max(1, options["limit"])
        queryset = Article.objects.order_by("-published_at", "-id")
        if options["only_missing"]:
            queryset = queryset.filter(passages__isnull=True)
        queryset = queryset.distinct()[:limit]

        processed = 0
        created = 0

        for article in queryset:
            passage_count = refresh_article_passages(article)
            processed += 1
            created += passage_count
            self.stdout.write(
                self.style.SUCCESS(
                    f"Processed article {article.id}: passages={passage_count} title={article.title[:60]}"
                )
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Passage backfill complete. processed={processed} passages_created={created} limit={limit}"
            )
        )
