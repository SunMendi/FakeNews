import feedparser
import fcntl
from pathlib import Path
from newspaper import Article as NewspaperArticle
from newspaper import Config as NewspaperConfig
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.timezone import make_aware
from django.utils.timezone import is_naive
from datetime import datetime
from claims.services.embeddings import embed_text
from news_sources.models import NewsSource, Article
from news_sources.services import build_article_text, refresh_article_passages

class Command(BaseCommand):
    help = "Fetch latest news from RSS feeds and store clean text"

    def add_arguments(self, parser):
        parser.add_argument(
            "--lock-file",
            default="/tmp/fetch_news.lock",
            help="File path used for process lock to prevent overlapping runs.",
        )

    def handle(self, *args, **options):
        lock_file_path = Path(options["lock_file"])
        lock_file_path.parent.mkdir(parents=True, exist_ok=True)

        # Prevent multiple instances from running concurrently.
        lock_file = open(lock_file_path, "w")

        try:
            # Try to acquire an exclusive lock without blocking.
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.stdout.write(
                self.style.WARNING("Another instance of fetch_news is already running. Exiting.")
            )
            return

        try:
            # 1. Get all your trusted newspapers from the database
            sources = NewsSource.objects.all()
            
            if not sources.exists():
                self.stdout.write(self.style.WARNING("No news sources found! Add some in the Django Admin first."))
                return

            for source in sources:
                self.stdout.write(f"Checking {source.name}...")
                
                # 2. Parse the RSS XML
                feed = feedparser.parse(source.rss_url)
                
                for entry in feed.entries:
                    url = entry.link
                    
                    # 3. Skip if we already have this article in our DB
                    if Article.objects.filter(url=url).exists():
                        continue

                    try:
                        # Use browser-like headers for sites that block default scraper agents.
                        config = NewspaperConfig()
                        config.browser_user_agent = (
                            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                            "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                        )
                        config.request_timeout = 15

                        # 4. Use newspaper4k to "Clean" the text
                        # It downloads the page and removes ads/menus automatically
                        news_item = NewspaperArticle(url, config=config)
                        news_item.download()
                        news_item.parse()
                        
                        # 5. Save it to our database
                        article_text = build_article_text(
                            title=(news_item.title or entry.title)[:500],
                            content=news_item.text,
                        )
                        with transaction.atomic():
                            article = Article.objects.create(
                                source=source,
                                title=(news_item.title or entry.title)[:500],
                                content=news_item.text,
                                embedding=self._build_embedding(article_text),
                                url=url,
                                published_at=self._get_publish_date(entry, news_item)
                            )
                            refresh_article_passages(article)
                        self.stdout.write(self.style.SUCCESS(f"  Successfully saved: {news_item.title[:50]}..."))

                    except Exception as e:
                        # Minimal fallback: keep the RSS record even if full-page scrape fails.
                        fallback_title = getattr(entry, "title", "Untitled")[:500]
                        fallback_content = (
                            getattr(entry, "summary", None)
                            or getattr(entry, "description", None)
                            or fallback_title
                        )
                        try:
                            article_text = build_article_text(
                                title=fallback_title,
                                content=fallback_content,
                            )
                            with transaction.atomic():
                                article = Article.objects.create(
                                    source=source,
                                    title=fallback_title,
                                    content=fallback_content,
                                    embedding=self._build_embedding(article_text),
                                    url=url,
                                    published_at=self._get_publish_date(entry, None),
                                )
                                refresh_article_passages(article)
                            self.stdout.write(self.style.WARNING(
                                f"  Saved from RSS fallback (scrape failed): {fallback_title[:50]}..."
                            ))
                        except Exception as save_error:
                            self.stdout.write(self.style.ERROR(f"  Error fetching {url}: {e}"))
                            self.stdout.write(self.style.ERROR(f"  Error saving fallback {url}: {save_error}"))
        finally:
            # Release the lock and close the file.
            fcntl.flock(lock_file, fcntl.LOCK_UN)
            lock_file.close()

    def _get_publish_date(self, entry, news_item):
        """Helper to find the best publication date"""
        if news_item and news_item.publish_date:
            if is_naive(news_item.publish_date):
                return make_aware(news_item.publish_date)
            return news_item.publish_date
        # If newspaper4k fails, try the RSS entry date
        if hasattr(entry, 'published_parsed'):
            return make_aware(datetime(*entry.published_parsed[:6]))
        return None

    def _build_embedding(self, text: str):
        if not text:
            return None
        try:
            return embed_text(text)
        except Exception as exc:
            self.stdout.write(self.style.WARNING(f"  Embedding generation failed: {exc}"))
            return None
