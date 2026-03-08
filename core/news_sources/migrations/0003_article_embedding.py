import pgvector.django.vector
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("claims", "0001_enable_postgres_extensions"),
        ("news_sources", "0002_alter_article_url"),
    ]

    operations = [
        migrations.AddField(
            model_name="article",
            name="embedding",
            field=pgvector.django.vector.VectorField(blank=True, dimensions=384, null=True),
        ),
    ]
