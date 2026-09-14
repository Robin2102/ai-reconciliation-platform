from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("ingestion", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="IngestFile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("path", models.CharField(max_length=500)),
                ("original_name", models.CharField(max_length=255)),
                ("source_type", models.CharField(default="csv", max_length=50)),
                ("source_id", models.CharField(db_index=True, max_length=100)),
                ("status", models.CharField(choices=[("staged", "Staged"), ("mapped", "Mapped"), ("ingesting", "Ingesting"), ("done", "Done"), ("error", "Error")], default="staged", max_length=20)),
                ("error_message", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="MappingTemplate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200)),
                ("source_id", models.CharField(db_index=True, max_length=100)),
                ("normalize_headers", models.BooleanField(default=True)),
                ("default_currency", models.CharField(default="INR", max_length=10)),
                ("dedupe", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["-updated_at"],
            },
        ),
        migrations.CreateModel(
            name="ColumnMapping",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("source_header", models.CharField(max_length=200)),
                ("detected_type", models.CharField(choices=[("string", "String"), ("date", "Date"), ("decimal", "Decimal"), ("integer", "Integer")], default="string", max_length=20)),
                ("role", models.CharField(choices=[("none", "None"), ("external_ref", "External Ref"), ("timestamp", "Timestamp"), ("cr_amount", "Cr Amount"), ("dr_amount", "Dr Amount"), ("amount", "Amount"), ("txn_type", "Txn Type"), ("currency", "Currency"), ("description", "Description"), ("ignore", "Ignore")], default="none", max_length=20)),
                ("mapped_name", models.CharField(blank=True, default="", max_length=200)),
                ("null_policy", models.CharField(choices=[("keep", "Keep"), ("empty_as_null", "Empty As Null")], default="keep", max_length=20)),
                ("date_format", models.CharField(blank=True, default="", max_length=40)),
                ("pii", models.CharField(choices=[("none", "None"), ("encrypt", "Encrypt")], default="none", max_length=20)),
                ("extra", models.JSONField(blank=True, default=dict)),
                ("template", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="columns", to="ingestion.mappingtemplate")),
            ],
            options={
                "ordering": ["id"],
                "unique_together": {("template", "source_header")},
            },
        ),
    ]
