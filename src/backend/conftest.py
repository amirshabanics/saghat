"""
Root conftest.py for the Saghat project test suite.

Provides shared fixtures for users, config, and common test data.
"""

import pytest
from decimal import Decimal


@pytest.fixture
def regular_user(db):
    """Create a regular (non-admin) test user."""
    from apps.users.models import User

    user = User.objects.create_user(
        username="testuser",
        password="testpass123",
        email="testuser@example.com",
        balance=Decimal("100.00000000"),
        is_main=False,
        loan_request_amount=Decimal("50.00000000"),
    )
    return user


@pytest.fixture
def main_user(db):
    """Create a main (admin) test user with is_main=True."""
    from apps.users.models import User

    user = User.objects.create_user(
        username="adminuser",
        password="adminpass123",
        email="admin@example.com",
        balance=Decimal("500.00000000"),
        is_main=True,
        loan_request_amount=Decimal("200.00000000"),
    )
    return user


@pytest.fixture
def config(db):
    """Create or retrieve the singleton Config object."""
    from apps.payments.models import Config

    config, _ = Config.objects.get_or_create(
        pk=1,
        defaults={
            "min_membership_fee": Decimal("20.00000000"),
            "max_month_for_loan_payment": 24,
            "min_amount_for_loan_payment": Decimal("20.00000000"),
        },
    )
    return config
