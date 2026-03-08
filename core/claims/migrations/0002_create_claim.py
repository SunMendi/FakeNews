import django.db.models.deletion
import pgvector.django.vector
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("claims", "0001_enable_postgres_extensions"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Claim",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("original_query", models.TextField()),
                ("normalized_query", models.TextField()),
                ("embedding", pgvector.django.vector.VectorField(blank=True, dimensions=384, null=True)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("verified", "Verified"), ("rejected", "Rejected")], default="pending", max_length=20)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="claims",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
    ]
