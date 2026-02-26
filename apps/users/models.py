from decimal import Decimal

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """
    Custom user model for Saghat fund members.

    balance: Running total of all membership fee payments made by this user.
             Increases with each MembershipFeePayment.
    is_main: Marks admin/special users who can see all loan history and create users.
    loan_request_amount: The USDT amount this user wants if they win the loan assignment.
                         Set to 0 or null if they don't want to participate.
    """

    balance: Decimal = models.DecimalField(
        max_digits=20, decimal_places=8, default=Decimal("0")
    )
    is_main: bool = models.BooleanField(default=False)
    loan_request_amount: Decimal = models.DecimalField(
        max_digits=20, decimal_places=8, default=Decimal("0")
    )

    class Meta:
        db_table = "users"

    def __str__(self) -> str:
        return self.username

    @property
    def has_active_loan(self) -> bool:
        """Check if user currently has an active (unpaid) loan."""
        from apps.loans.models import LoanState

        return self.loans.filter(state=LoanState.ACTIVE).exists()
