from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ingestion", "0002_ingestfile_mappingtemplate_columnmapping"),
    ]

    operations = [
        migrations.AlterField(
            model_name="columnmapping",
            name="source_header",
            field=models.CharField(max_length=1024),
        ),
        migrations.AlterField(
            model_name="columnmapping",
            name="mapped_name",
            field=models.CharField(blank=True, default="", max_length=1024),
        ),
    ]
