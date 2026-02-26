import uuid
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("loans", "0001_initial"),
        ("users", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Config",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "min_membership_fee",
                    models.DecimalField(
                        decimal_places=8, default=Decimal("20"), max_digits=20
                    ),
                ),
                (
                    "max_month_for_loan_payment",
                    models.PositiveIntegerField(default=24),
                ),
                (
                    "min_amount_for_loan_payment",
                    models.DecimalField(
                        decimal_places=8, default=Decimal("20"), max_digits=20
                    ),
                ),
            ],
            options={
                "db_table": "config",
            },
        ),
        migrations.CreateModel(
            name="Payment",
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
                    models.DecimalField(decimal_places=8, max_digits=20),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("jalali_year", models.PositiveIntegerField()),
                ("jalali_month", models.PositiveIntegerField()),
                ("bitpin_payment_id", models.CharField(max_length=255)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="payments",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "payments",
                "unique_together": {("user", "jalali_year", "jalali_month")},
            },
        ),
        migrations.CreateModel(
            name="MembershipFeePayment",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "amount",
                    models.DecimalField(decimal_places=8, max_digits=20),
                ),
                (
                    "payment",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="membership_fee",
                        to="payments.payment",
                    ),
                ),
            ],
            options={
                "db_table": "membership_fee_payments",
            },
        ),
        migrations.CreateModel(
            name="LoanPayment",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "amount",
                    models.DecimalField(decimal_places=8, max_digits=20),
                ),
                (
                    "loan",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="payments",
                        to="loans.loan",
                    ),
                ),
                (
                    "payment",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="loan_payment",
                        to="payments.payment",
                    ),
                ),
            ],
            options={
                "db_table": "loan_payments",
            },
        ),
    ]
