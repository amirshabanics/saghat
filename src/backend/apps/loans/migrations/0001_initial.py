import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("users", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Loan",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "amount",
                    models.DecimalField(
                        blank=True, decimal_places=8, max_digits=20, null=True
                    ),
                ),
                (
                    "state",
                    models.CharField(
                        choices=[
                            ("initial", "Initial"),
                            ("active", "Active"),
                            ("no_one", "No One"),
                        ],
                        default="initial",
                        max_length=20,
                    ),
                ),
                ("jalali_year", models.PositiveIntegerField()),
                ("jalali_month", models.PositiveIntegerField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "min_amount_for_each_payment",
                    models.DecimalField(
                        blank=True, decimal_places=8, max_digits=20, null=True
                    ),
                ),
                ("log", models.JSONField(default=dict)),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="loans",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "loans",
                "unique_together": {("jalali_year", "jalali_month")},
            },
        ),
    ]
