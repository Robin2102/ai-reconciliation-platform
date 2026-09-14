import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ingestion", "0002_ingestfile_mappingtemplate_columnmapping"),
        ("reconciliation", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="transaction",
            name="ingest_file",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="transactions",
                to="ingestion.ingestfile",
            ),
        ),
    ]
