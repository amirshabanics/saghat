import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models


class LoanState(models.TextChoices):
    INITIAL = "initial", "Initial"
    ACTIVE = "active", "Active"
    NO_ONE = "no_one", "No One"


class Loan(models.Model):
    """
    Represents a monthly loan assignment.

    States:
    - initial: Loan assignment process has been triggered for this month
    - active: A user has been assigned the loan and is repaying it
    - no_one: No eligible user could receive the loan this month

    log: JSON audit trail of the assignment process containing:
         - not_participated: list of {user_id, username, reason}
         - participated: list of {user_id, username, point}
         - selected: user_id of winner or null
         - random_pool: list of user_ids that were in the random selection pool

    min_amount_for_each_payment: Copied from Config at time of loan creation.
    """

    id: uuid.UUID = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="loans",
        null=True,
        blank=True,
    )
    amount: Decimal = models.DecimalField(
        max_digits=20, decimal_places=8, null=True, blank=True
    )
    state: str = models.CharField(
        max_length=20,
        choices=LoanState.choices,
        default=LoanState.INITIAL,
    )
    jalali_year: int = models.PositiveIntegerField()
    jalali_month: int = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    min_amount_for_each_payment: Decimal = models.DecimalField(
        max_digits=20, decimal_places=8, null=True, blank=True
    )
    log = models.JSONField(default=dict)

    class Meta:
        db_table = "loans"
        unique_together = [("jalali_year", "jalali_month")]

    def __str__(self) -> str:
        return f"Loan({self.jalali_year}/{self.jalali_month}, state={self.state}, user={self.user_id})"

    @property
    def total_paid(self) -> Decimal:
        """Sum of all loan payments made so far."""
        from django.db.models import Sum

        result = self.payments.aggregate(total=Sum("amount"))["total"]
        return result or Decimal("0")

    @property
    def remaining_balance(self) -> Decimal:
        """Remaining amount to be repaid."""
        if self.amount is None:
            return Decimal("0")
        return self.amount - self.total_paid

    @property
    def is_settled(self) -> bool:
        """Whether the loan has been fully repaid."""
        return self.remaining_balance <= Decimal("0")
