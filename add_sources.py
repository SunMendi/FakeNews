import os
import sys
import django

# Add the 'core' directory to the Python path
sys.path.append(os.path.join(os.getcwd(), 'core'))

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from news_sources.models import NewsSource

# 1. Your updated list of 10 newspapers
sources_data = [
    ("The Daily Star", "https://www.thedailystar.net/rss.xml"),
    ("The Business Standard", "https://www.tbsnews.net/rss.xml"),
    ("Dhaka Tribune", "https://www.dhakatribune.com/feed/"),
    ("Bangla Tribune", "https://www.banglatribune.com/feed/"),
    ("The Daily Ittefaq", "https://www.ittefaq.com.bd/feed/"),
    ("Dhaka Post", "https://www.dhakapost.com/rss/rss.xml"),
    ("Samakal", "https://www.samakal.com/rss"),
    ("Prothom Alo", "https://www.prothomalo.com/feed"),
    ("Prothom Alo English", "https://en.prothomalo.com/feed"),
    ("Kalbela", "https://www.kalbela.com/rss/latest-rss.xml"),
]

# 2. Track which ones we updated
current_urls = [url for name, url in sources_data]

for name, url in sources_data:
    # update_or_create will:
    # - Find the record by 'name'
    # - If found, update it with the new 'rss_url'
    # - If NOT found, create a new record
    obj, created = NewsSource.objects.update_or_create(
        name=name, 
        defaults={'rss_url': url}
    )
    
    if created:
        print(f"Added {name}")
    else:
        print(f"Updated {name}")

# 3. (Optional) Remove sources that are no longer in your list
# If you want to keep your database "Pure" with only these 10:
# NewsSource.objects.exclude(rss_url__in=current_urls).delete()
