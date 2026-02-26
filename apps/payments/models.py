import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models


class Config(models.Model):
    """
    Singleton configuration model for the fund.
    Only one instance should exist. Use Config.get_config() to retrieve it.
    """

    min_membership_fee: Decimal = models.DecimalField(
        max_digits=20, decimal_places=8, default=Decimal("20")
    )
    max_month_for_loan_payment: int = models.PositiveIntegerField(default=24)
    min_amount_for_loan_payment: Decimal = models.DecimalField(
        max_digits=20, decimal_places=8, default=Decimal("20")
    )

    class Meta:
        db_table = "config"

    @classmethod
    def get_config(cls) -> "Config":
        """Get or create the singleton config instance."""
        config, _ = cls.objects.get_or_create(pk=1)
        return config

    def __str__(self) -> str:
        return f"Config(min_fee={self.min_membership_fee})"


class Payment(models.Model):
    """
    Base payment record. Every financial transaction creates a Payment.
    Can be associated with a MembershipFeePayment and/or LoanPayment.

    jalali_year/jalali_month: Derived from created_at using jdatetime.
    bitpin_payment_id: The payment ID from Bitpin exchange for verification.
    """

    id: uuid.UUID = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="payments",
    )
    amount: Decimal = models.DecimalField(max_digits=20, decimal_places=8)
    created_at = models.DateTimeField(auto_now_add=True)
    jalali_year: int = models.PositiveIntegerField()
    jalali_month: int = models.PositiveIntegerField()
    bitpin_payment_id: str = models.CharField(max_length=255)

    class Meta:
        db_table = "payments"
        # Each user can only have one payment record per Jalali month
        unique_together = [("user", "jalali_year", "jalali_month")]

    def __str__(self) -> str:
        return f"Payment({self.user_id}, {self.jalali_year}/{self.jalali_month}, {self.amount})"


class MembershipFeePayment(models.Model):
    """
    The membership fee portion of a payment.
    Linked 1:1 to a Payment record.
    amount must be >= Config.min_membership_fee (validated at API level).
    """

    payment = models.OneToOneField(
        Payment,
        on_delete=models.CASCADE,
        related_name="membership_fee",
    )
    amount: Decimal = models.DecimalField(max_digits=20, decimal_places=8)

    class Meta:
        db_table = "membership_fee_payments"

    def __str__(self) -> str:
        return f"MembershipFee({self.payment_id}, {self.amount})"


class LoanPayment(models.Model):
    """
    The loan repayment portion of a payment.
    Linked 1:1 to a Payment record and FK to the Loan being repaid.
    amount must be >= Loan.min_amount_for_each_payment (validated at API level).
    """

    payment = models.OneToOneField(
        Payment,
        on_delete=models.CASCADE,
        related_name="loan_payment",
    )
    loan = models.ForeignKey(
        "loans.Loan",
        on_delete=models.PROTECT,
        related_name="payments",
    )
    amount: Decimal = models.DecimalField(max_digits=20, decimal_places=8)

    class Meta:
        db_table = "loan_payments"

    def __str__(self) -> str:
        return f"LoanPayment({self.payment_id}, loan={self.loan_id}, {self.amount})"
