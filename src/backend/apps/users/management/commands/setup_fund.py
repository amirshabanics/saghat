"""
Management command to set up initial fund configuration.
Usage: python manage.py setup_fund
"""

from decimal import Decimal
from typing import Any

from django.core.management.base import BaseCommand

from apps.payments.models import Config


class Command(BaseCommand):
    help = "Set up initial fund configuration"

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--min-fee",
            type=Decimal,
            default=Decimal("20"),
            help="Minimum monthly membership fee in USDT (default: 20)",
        )
        parser.add_argument(
            "--max-months",
            type=int,
            default=24,
            help="Maximum loan repayment months (default: 24)",
        )
        parser.add_argument(
            "--min-payment",
            type=Decimal,
            default=Decimal("20"),
            help="Minimum monthly loan payment in USDT (default: 20)",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        config, created = Config.objects.get_or_create(pk=1)
        config.min_membership_fee = options["min_fee"]
        config.max_month_for_loan_payment = options["max_months"]
        config.min_amount_for_loan_payment = options["min_payment"]
        config.save()

        action = "Created" if created else "Updated"
        self.stdout.write(
            self.style.SUCCESS(
                f"{action} fund config: "
                f"min_fee={config.min_membership_fee} USDT, "
                f"max_months={config.max_month_for_loan_payment}, "
                f"min_payment={config.min_amount_for_loan_payment} USDT"
            )
        )
