from django.db import migrations


class Migration(migrations.Migration):
    #every migrations file must have a migration class 
    initial = True
    #marks this is the first migration for this app

    dependencies = []

    #this migration does not depend on earlier migrations 

    operations = [
        migrations.RunSQL(
            sql="CREATE EXTENSION IF NOT EXISTS pg_trgm;",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql="CREATE EXTENSION IF NOT EXISTS vector;",
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
