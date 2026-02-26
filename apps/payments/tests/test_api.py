"""
End-to-end API tests for the Payments API.

Tests cover:
- GET /api/payments/config
- GET /api/payments/my-payments
- POST /api/payments/pay
"""

from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.test import TestCase

from ninja.testing import TestClient

from apps.payments.api import router
from apps.payments.models import Config, Payment, MembershipFeePayment
from apps.loans.models import Loan, LoanState
from apps.common.auth import create_access_token


client = TestClient(router)


def auth_headers(user) -> dict:
    """Return Authorization headers for the given user."""
    token = create_access_token(user.id)
    return {"Authorization": f"Bearer {token}"}


def make_user(username="payuser", is_main=False, balance=Decimal("100.00")):
    from apps.users.models import User
    return User.objects.create_user(
        username=username,
        password="paypass123",
        email=f"{username}@example.com",
        is_main=is_main,
        balance=balance,
        loan_request_amount=Decimal("50.00"),
    )


def make_config(
    min_membership_fee=Decimal("20.00"),
    max_month_for_loan_payment=24,
    min_amount_for_loan_payment=Decimal("20.00"),
):
    config, _ = Config.objects.get_or_create(
        pk=1,
        defaults={
            "min_membership_fee": min_membership_fee,
            "max_month_for_loan_payment": max_month_for_loan_payment,
            "min_amount_for_loan_payment": min_amount_for_loan_payment,
        },
    )
    return config


class TestGetConfig(TestCase):
    """Tests for GET /config"""

    def setUp(self):
        self.user = make_user("configuser")
        self.config = make_config()

    def test_get_config_authenticated(self):
        response = client.get(
            "/config",
            headers=auth_headers(self.user),
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("min_membership_fee", data)
        self.assertIn("max_month_for_loan_payment", data)
        self.assertIn("min_amount_for_loan_payment", data)

    def test_get_config_values(self):
        response = client.get(
            "/config",
            headers=auth_headers(self.user),
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(Decimal(data["min_membership_fee"]), Decimal("20.00"))
        self.assertEqual(data["max_month_for_loan_payment"], 24)
        self.assertEqual(Decimal(data["min_amount_for_loan_payment"]), Decimal("20.00"))

    def test_get_config_no_auth(self):
        response = client.get("/config")
        self.assertEqual(response.status_code, 401)

    def test_get_config_invalid_token(self):
        response = client.get(
            "/config",
            headers={"Authorization": "Bearer invalidtoken"},
        )
        self.assertEqual(response.status_code, 401)


class TestListMyPayments(TestCase):
    """Tests for GET /my-payments"""

    def setUp(self):
        self.user1 = make_user("mypayuser1")
        self.user2 = make_user("mypayuser2")
        self.config = make_config()

        # Create payments for user1
        self.payment1 = Payment.objects.create(
            user=self.user1,
            amount=Decimal("30.00"),
            jalali_year=1402,
            jalali_month=1,
            bitpin_payment_id="bitpin-001",
        )
        MembershipFeePayment.objects.create(
            payment=self.payment1,
            amount=Decimal("30.00"),
        )

        self.payment2 = Payment.objects.create(
            user=self.user1,
            amount=Decimal("25.00"),
            jalali_year=1402,
            jalali_month=2,
            bitpin_payment_id="bitpin-002",
        )
        MembershipFeePayment.objects.create(
            payment=self.payment2,
            amount=Decimal("25.00"),
        )

        # Create a payment for user2
        self.payment3 = Payment.objects.create(
            user=self.user2,
            amount=Decimal("20.00"),
            jalali_year=1402,
            jalali_month=1,
            bitpin_payment_id="bitpin-003",
        )
        MembershipFeePayment.objects.create(
            payment=self.payment3,
            amount=Decimal("20.00"),
        )

    def test_list_my_payments_returns_only_own_payments(self):
        response = client.get(
            "/my-payments",
            headers=auth_headers(self.user1),
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 2)
        for payment in data:
            self.assertEqual(payment["user_id"], self.user1.id)

    def test_list_my_payments_empty_for_new_user(self):
        new_user = make_user("newpayuser")
        response = client.get(
            "/my-payments",
            headers=auth_headers(new_user),
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data, [])

    def test_list_my_payments_no_auth(self):
        response = client.get("/my-payments")
        self.assertEqual(response.status_code, 401)

    def test_list_my_payments_response_fields(self):
        response = client.get(
            "/my-payments",
            headers=auth_headers(self.user1),
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertGreater(len(data), 0)
        payment_data = data[0]
        expected_fields = [
            "id", "user_id", "amount", "jalali_year", "jalali_month",
            "bitpin_payment_id", "membership_fee", "loan_payment"
        ]
        for field in expected_fields:
            self.assertIn(field, payment_data)

    def test_list_my_payments_does_not_include_other_users(self):
        response = client.get(
            "/my-payments",
            headers=auth_headers(self.user2),
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["user_id"], self.user2.id)


class TestPay(TestCase):
    """Tests for POST /pay"""

    def setUp(self):
        self.user = make_user("paysubmituser", balance=Decimal("0.00"))
        self.config = make_config(min_membership_fee=Decimal("20.00"))

    @patch("apps.payments.api.get_current_jalali")
    def test_pay_success_no_bitpin_key(self, mock_jalali):
        """Payment succeeds when BITPIN_API_KEY is not set (dev mode)."""
        mock_jalali_obj = MagicMock()
        mock_jalali_obj.year = 1403
        mock_jalali_obj.month = 1
        mock_jalali.return_value = mock_jalali_obj

        response = client.post(
            "/pay",
            json={
                "membership_fee": "25.00",
                "bitpin_payment_id": "test-bitpin-001",
            },
            headers=auth_headers(self.user),
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertIn("id", data)
        self.assertEqual(data["user_id"], self.user.id)
        self.assertEqual(Decimal(data["amount"]), Decimal("25.00"))
        self.assertEqual(data["jalali_year"], 1403)
        self.assertEqual(data["jalali_month"], 1)
        self.assertIsNotNone(data["membership_fee"])
        self.assertIsNone(data["loan_payment"])

    @patch("apps.payments.api.get_current_jalali")
    def test_pay_updates_user_balance(self, mock_jalali):
        """Payment increases user balance by membership_fee."""
        mock_jalali_obj = MagicMock()
        mock_jalali_obj.year = 1403
        mock_jalali_obj.month = 2
        mock_jalali.return_value = mock_jalali_obj

        initial_balance = self.user.balance
        client.post(
            "/pay",
            json={
                "membership_fee": "30.00",
                "bitpin_payment_id": "test-bitpin-002",
            },
            headers=auth_headers(self.user),
        )
        self.user.refresh_from_db()
        self.assertEqual(self.user.balance, initial_balance + Decimal("30.00"))

    @patch("apps.payments.api.get_current_jalali")
    def test_pay_duplicate_payment_same_month(self, mock_jalali):
        """Returns 409 if user already paid for this month."""
        mock_jalali_obj = MagicMock()
        mock_jalali_obj.year = 1403
        mock_jalali_obj.month = 3
        mock_jalali.return_value = mock_jalali_obj

        # First payment
        client.post(
            "/pay",
            json={
                "membership_fee": "25.00",
                "bitpin_payment_id": "test-bitpin-003a",
            },
            headers=auth_headers(self.user),
        )

        # Second payment same month
        response = client.post(
            "/pay",
            json={
                "membership_fee": "25.00",
                "bitpin_payment_id": "test-bitpin-003b",
            },
            headers=auth_headers(self.user),
        )
        self.assertEqual(response.status_code, 409)
        data = response.json()
        self.assertIn("detail", data)

    @patch("apps.payments.api.get_current_jalali")
    def test_pay_membership_fee_below_minimum(self, mock_jalali):
        """Returns 400 if membership_fee is below minimum."""
        mock_jalali_obj = MagicMock()
        mock_jalali_obj.year = 1403
        mock_jalali_obj.month = 4
        mock_jalali.return_value = mock_jalali_obj

        response = client.post(
            "/pay",
            json={
                "membership_fee": "10.00",  # Below min of 20.00
                "bitpin_payment_id": "test-bitpin-004",
            },
            headers=auth_headers(self.user),
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("detail", data)
        self.assertIn("minimum", data["detail"])

    @patch("apps.payments.api.get_current_jalali")
    def test_pay_loan_payment_without_active_loan(self, mock_jalali):
        """Returns 400 if loan payment provided but user has no active loan."""
        mock_jalali_obj = MagicMock()
        mock_jalali_obj.year = 1403
        mock_jalali_obj.month = 5
        mock_jalali.return_value = mock_jalali_obj

        response = client.post(
            "/pay",
            json={
                "membership_fee": "25.00",
                "loan": "50.00",
                "bitpin_payment_id": "test-bitpin-005",
            },
            headers=auth_headers(self.user),
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("detail", data)
        self.assertIn("active loan", data["detail"])

    @patch("apps.payments.api.get_current_jalali")
    def test_pay_missing_loan_payment_with_active_loan(self, mock_jalali):
        """Returns 400 if user has active loan but no loan payment provided."""
        mock_jalali_obj = MagicMock()
        mock_jalali_obj.year = 1403
        mock_jalali_obj.month = 6
        mock_jalali.return_value = mock_jalali_obj

        # Create an active loan for the user
        Loan.objects.create(
            user=self.user,
            state=LoanState.ACTIVE,
            jalali_year=1402,
            jalali_month=1,
            amount=Decimal("200.00"),
            min_amount_for_each_payment=Decimal("20.00"),
            log={},
        )

        response = client.post(
            "/pay",
            json={
                "membership_fee": "25.00",
                "bitpin_payment_id": "test-bitpin-006",
            },
            headers=auth_headers(self.user),
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("detail", data)
        self.assertIn("active loan", data["detail"])

    @patch("apps.payments.api.get_current_jalali")
    def test_pay_loan_payment_below_minimum(self, mock_jalali):
        """Returns 400 if loan payment is below minimum required."""
        mock_jalali_obj = MagicMock()
        mock_jalali_obj.year = 1403
        mock_jalali_obj.month = 7
        mock_jalali.return_value = mock_jalali_obj

        # Create an active loan with min_amount_for_each_payment = 20
        Loan.objects.create(
            user=self.user,
            state=LoanState.ACTIVE,
            jalali_year=1402,
            jalali_month=2,
            amount=Decimal("200.00"),
            min_amount_for_each_payment=Decimal("20.00"),
            log={},
        )

        response = client.post(
            "/pay",
            json={
                "membership_fee": "25.00",
                "loan": "5.00",  # Below min of 20.00
                "bitpin_payment_id": "test-bitpin-007",
            },
            headers=auth_headers(self.user),
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("detail", data)
        self.assertIn("minimum", data["detail"])

    @patch("apps.payments.api.get_current_jalali")
    def test_pay_with_active_loan_success(self, mock_jalali):
        """Payment with loan repayment succeeds when user has active loan."""
        mock_jalali_obj = MagicMock()
        mock_jalali_obj.year = 1403
        mock_jalali_obj.month = 8
        mock_jalali.return_value = mock_jalali_obj

        # Create an active loan
        Loan.objects.create(
            user=self.user,
            state=LoanState.ACTIVE,
            jalali_year=1402,
            jalali_month=3,
            amount=Decimal("200.00"),
            min_amount_for_each_payment=Decimal("20.00"),
            log={},
        )

        response = client.post(
            "/pay",
            json={
                "membership_fee": "25.00",
                "loan": "25.00",
                "bitpin_payment_id": "test-bitpin-008",
            },
            headers=auth_headers(self.user),
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(Decimal(data["amount"]), Decimal("50.00"))  # 25 + 25
        self.assertIsNotNone(data["loan_payment"])
        self.assertEqual(Decimal(data["loan_payment"]["amount"]), Decimal("25.00"))

    @patch("apps.payments.api.get_current_jalali")
    def test_pay_updates_loan_request_amount(self, mock_jalali):
        """Payment with loan_request_amount updates user's loan_request_amount."""
        mock_jalali_obj = MagicMock()
        mock_jalali_obj.year = 1403
        mock_jalali_obj.month = 9
        mock_jalali.return_value = mock_jalali_obj

        client.post(
            "/pay",
            json={
                "membership_fee": "25.00",
                "loan_request_amount": "100.00",
                "bitpin_payment_id": "test-bitpin-009",
            },
            headers=auth_headers(self.user),
        )
        self.user.refresh_from_db()
        self.assertEqual(self.user.loan_request_amount, Decimal("100.00"))

    def test_pay_no_auth(self):
        response = client.post(
            "/pay",
            json={
                "membership_fee": "25.00",
                "bitpin_payment_id": "test-bitpin-noauth",
            },
        )
        self.assertEqual(response.status_code, 401)

    def test_pay_missing_required_fields(self):
        response = client.post(
            "/pay",
            json={"membership_fee": "25.00"},
            headers=auth_headers(self.user),
        )
        self.assertEqual(response.status_code, 422)

    @patch("apps.payments.api.app_settings")
    @patch("apps.payments.api.get_bitpin_client")
    @patch("apps.payments.api.get_current_jalali")
    def test_pay_bitpin_verification_success(self, mock_jalali, mock_get_client, mock_settings):
        """Payment succeeds when Bitpin verification passes."""
        mock_jalali_obj = MagicMock()
        mock_jalali_obj.year = 1403
        mock_jalali_obj.month = 10
        mock_jalali.return_value = mock_jalali_obj

        mock_settings.BITPIN_API_KEY = "test-api-key"

        mock_bitpin = MagicMock()
        mock_bitpin.verify_payment_amount.return_value = (True, None)
        mock_get_client.return_value = mock_bitpin

        response = client.post(
            "/pay",
            json={
                "membership_fee": "25.00",
                "bitpin_payment_id": "bitpin-verified-001",
            },
            headers=auth_headers(self.user),
        )
        self.assertEqual(response.status_code, 201)
        mock_bitpin.verify_payment_amount.assert_called_once_with(
            "bitpin-verified-001", Decimal("25.00")
        )

    @patch("apps.payments.api.app_settings")
    @patch("apps.payments.api.get_bitpin_client")
    @patch("apps.payments.api.get_current_jalali")
    def test_pay_bitpin_verification_failure(self, mock_jalali, mock_get_client, mock_settings):
        """Payment fails when Bitpin verification fails."""
        mock_jalali_obj = MagicMock()
        mock_jalali_obj.year = 1403
        mock_jalali_obj.month = 11
        mock_jalali.return_value = mock_jalali_obj

        mock_settings.BITPIN_API_KEY = "test-api-key"

        mock_bitpin = MagicMock()
        mock_bitpin.verify_payment_amount.return_value = (False, "Amount mismatch")
        mock_get_client.return_value = mock_bitpin

        response = client.post(
            "/pay",
            json={
                "membership_fee": "25.00",
                "bitpin_payment_id": "bitpin-invalid-001",
            },
            headers=auth_headers(self.user),
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("detail", data)
        self.assertIn("Bitpin payment verification failed", data["detail"])
        self.assertIn("Amount mismatch", data["detail"])
