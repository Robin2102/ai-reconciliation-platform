from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ingestion", "0003_widen_column_headers"),
    ]

    operations = [
        migrations.AlterField(
            model_name="columnmapping",
            name="role",
            field=models.CharField(
                choices=[
                    ("none", "None"),
                    ("external_ref", "External Ref"),
                    ("timestamp", "Timestamp"),
                    ("date_year", "Date Year"),
                    ("date_month", "Date Month"),
                    ("date_day", "Date Day"),
                    ("time", "Time"),
                    ("cr_amount", "Cr Amount"),
                    ("dr_amount", "Dr Amount"),
                    ("amount", "Amount"),
                    ("txn_type", "Txn Type"),
                    ("currency", "Currency"),
                    ("description", "Description"),
                    ("ignore", "Ignore"),
                ],
                default="none",
                max_length=20,
            ),
        ),
    ]
