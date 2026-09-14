import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ingestion", "0004_column_roles_ymd_time"),
    ]

    operations = [
        migrations.AddField(
            model_name="rawrecord",
            name="ingest_file",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="raw_records",
                to="ingestion.ingestfile",
            ),
        ),
    ]
