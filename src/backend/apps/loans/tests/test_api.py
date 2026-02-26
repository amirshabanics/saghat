"""
End-to-end API tests for the Loans API.

Tests cover:
- POST /api/loans/start
- GET /api/loans/history
- GET /api/loans/my-history
- GET /api/loans/{loan_id}
"""

import uuid
from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.test import TestCase

from ninja.testing import TestClient

from apps.loans.api import router
from apps.loans.models import Loan, LoanState
from apps.common.auth import create_access_token


client = TestClient(router)


def auth_headers(user) -> dict:
    """Return Authorization headers for the given user."""
    token = create_access_token(user.id)
    return {"Authorization": f"Bearer {token}"}


def make_main_user(username="mainadmin", password="adminpass123"):
    from apps.users.models import User

    return User.objects.create_user(
        username=username,
        password=password,
        email=f"{username}@example.com",
        is_main=True,
        balance=Decimal("500.00"),
        loan_request_amount=Decimal("200.00"),
    )


def make_regular_user(username="regularuser", password="regularpass123"):
    from apps.users.models import User

    return User.objects.create_user(
        username=username,
        password=password,
        email=f"{username}@example.com",
        is_main=False,
        balance=Decimal("100.00"),
        loan_request_amount=Decimal("50.00"),
    )


def make_loan(
    user=None,
    state=LoanState.ACTIVE,
    year=1403,
    month=1,
    amount=Decimal("100.00"),
):
    """Create a Loan record for testing."""
    return Loan.objects.create(
        user=user,
        state=state,
        jalali_year=year,
        jalali_month=month,
        amount=amount,
        min_amount_for_each_payment=Decimal("10.00"),
        log={},
    )


class TestStartLoanAssignment(TestCase):
    """Tests for POST /start"""

    def setUp(self):
        self.main_user = make_main_user("startadmin")
        self.regular_user = make_regular_user("startregular")

    @patch("apps.loans.api.run_loan_assignment")
    @patch("apps.loans.api.get_current_jalali")
    def test_start_loan_assignment_success(self, mock_jalali, mock_run):
        """Any authenticated user can trigger loan assignment."""
        mock_jalali_obj = MagicMock()
        mock_jalali_obj.year = 1403
        mock_jalali_obj.month = 6
        mock_jalali.return_value = mock_jalali_obj

        loan = make_loan(
            user=self.regular_user,
            state=LoanState.ACTIVE,
            year=1403,
            month=6,
        )
        mock_run.return_value = loan

        response = client.post(
            "/start",
            headers=auth_headers(self.regular_user),
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertIn("loan", data)
        self.assertIn("message", data)
        self.assertEqual(data["loan"]["state"], LoanState.ACTIVE)

    @patch("apps.loans.api.run_loan_assignment")
    @patch("apps.loans.api.get_current_jalali")
    def test_start_loan_assignment_no_one_eligible(
        self, mock_jalali, mock_run
    ):
        """Returns 201 with no_one state when no eligible user found."""
        mock_jalali_obj = MagicMock()
        mock_jalali_obj.year = 1403
        mock_jalali_obj.month = 7
        mock_jalali.return_value = mock_jalali_obj

        loan = make_loan(
            user=None,
            state=LoanState.NO_ONE,
            year=1403,
            month=7,
            amount=None,
        )
        mock_run.return_value = loan

        response = client.post(
            "/start",
            headers=auth_headers(self.regular_user),
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["loan"]["state"], LoanState.NO_ONE)

    @patch("apps.loans.api.get_current_jalali")
    def test_start_loan_assignment_already_done(self, mock_jalali):
        """Returns 409 if loan assignment already done for this month."""
        mock_jalali_obj = MagicMock()
        mock_jalali_obj.year = 1403
        mock_jalali_obj.month = 8
        mock_jalali.return_value = mock_jalali_obj

        # Pre-create a loan for this month
        make_loan(
            year=1403, month=8, state=LoanState.ACTIVE, user=self.regular_user
        )

        response = client.post(
            "/start",
            headers=auth_headers(self.regular_user),
        )
        self.assertEqual(response.status_code, 409)
        data = response.json()
        self.assertIn("detail", data)

    @patch("apps.loans.api.run_loan_assignment")
    @patch("apps.loans.api.get_current_jalali")
    def test_start_loan_assignment_value_error(self, mock_jalali, mock_run):
        """Returns 400 if run_loan_assignment raises ValueError."""
        mock_jalali_obj = MagicMock()
        mock_jalali_obj.year = 1403
        mock_jalali_obj.month = 9
        mock_jalali.return_value = mock_jalali_obj

        mock_run.side_effect = ValueError("Not all users have paid this month")

        response = client.post(
            "/start",
            headers=auth_headers(self.regular_user),
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("detail", data)
        self.assertIn("Not all users have paid", data["detail"])

    def test_start_loan_assignment_no_auth(self):
        response = client.post("/start")
        self.assertEqual(response.status_code, 401)

    def test_start_loan_assignment_invalid_token(self):
        response = client.post(
            "/start",
            headers={"Authorization": "Bearer invalidtoken"},
        )
        self.assertEqual(response.status_code, 401)


class TestGetAllLoanHistory(TestCase):
    """Tests for GET /history"""

    def setUp(self):
        self.main_user = make_main_user("historyadmin")
        self.regular_user = make_regular_user("historyregular")

        # Create some loans
        self.loan1 = make_loan(
            user=self.regular_user,
            state=LoanState.ACTIVE,
            year=1402,
            month=1,
            amount=Decimal("100.00"),
        )
        self.loan2 = make_loan(
            user=self.regular_user,
            state=LoanState.NO_ONE,
            year=1402,
            month=2,
            amount=None,
        )
        self.loan3 = make_loan(
            user=self.regular_user,
            state=LoanState.ACTIVE,
            year=1403,
            month=1,
            amount=Decimal("200.00"),
        )

    def test_get_all_loan_history_as_main_user(self):
        response = client.get(
            "/history",
            headers=auth_headers(self.main_user),
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 3)

    def test_get_all_loan_history_unauthorized_regular_user(self):
        response = client.get(
            "/history",
            headers=auth_headers(self.regular_user),
        )
        self.assertEqual(response.status_code, 401)

    def test_get_all_loan_history_no_auth(self):
        response = client.get("/history")
        self.assertEqual(response.status_code, 401)

    def test_get_all_loan_history_filter_year_gt(self):
        response = client.get(
            "/history?jalali_year_gt=1402",
            headers=auth_headers(self.main_user),
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        # Only loan3 (year=1403) should be returned
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["jalali_year"], 1403)

    def test_get_all_loan_history_filter_year_lt(self):
        response = client.get(
            "/history?jalali_year_lt=1403",
            headers=auth_headers(self.main_user),
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        # loan1 and loan2 (year=1402) should be returned
        self.assertEqual(len(data), 2)
        for item in data:
            self.assertEqual(item["jalali_year"], 1402)

    def test_get_all_loan_history_filter_month_gt(self):
        response = client.get(
            "/history?jalali_month_gt=1",
            headers=auth_headers(self.main_user),
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        # Only loan2 (month=2) should be returned
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["jalali_month"], 2)

    def test_get_all_loan_history_response_fields(self):
        response = client.get(
            "/history",
            headers=auth_headers(self.main_user),
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertGreater(len(data), 0)
        loan_data = data[0]
        expected_fields = [
            "id",
            "user_id",
            "username",
            "amount",
            "state",
            "jalali_year",
            "jalali_month",
            "min_amount_for_each_payment",
            "total_paid",
            "remaining_balance",
            "log",
            "payments",
        ]
        for field in expected_fields:
            self.assertIn(field, loan_data)


class TestGetMyLoanHistory(TestCase):
    """Tests for GET /my-history"""

    def setUp(self):
        self.user1 = make_regular_user("myhistoryuser1")
        self.user2 = make_regular_user("myhistoryuser2")

        # Create loans for user1
        self.loan1 = make_loan(
            user=self.user1,
            state=LoanState.ACTIVE,
            year=1402,
            month=3,
            amount=Decimal("100.00"),
        )
        self.loan2 = make_loan(
            user=self.user1,
            state=LoanState.ACTIVE,
            year=1402,
            month=4,
            amount=Decimal("150.00"),
        )
        # Create a loan for user2
        self.loan3 = make_loan(
            user=self.user2,
            state=LoanState.ACTIVE,
            year=1402,
            month=5,
            amount=Decimal("200.00"),
        )

    def test_get_my_loan_history_returns_only_own_loans(self):
        response = client.get(
            "/my-history",
            headers=auth_headers(self.user1),
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 2)
        for loan in data:
            self.assertEqual(loan["user_id"], self.user1.id)

    def test_get_my_loan_history_empty_for_new_user(self):
        new_user = make_regular_user("newhistoryuser")
        response = client.get(
            "/my-history",
            headers=auth_headers(new_user),
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data, [])

    def test_get_my_loan_history_no_auth(self):
        response = client.get("/my-history")
        self.assertEqual(response.status_code, 401)

    def test_get_my_loan_history_does_not_include_other_users(self):
        response = client.get(
            "/my-history",
            headers=auth_headers(self.user2),
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["user_id"], self.user2.id)


class TestGetLoanDetail(TestCase):
    """Tests for GET /{loan_id}"""

    def setUp(self):
        self.main_user = make_main_user("detailadmin")
        self.user1 = make_regular_user("detailuser1")
        self.user2 = make_regular_user("detailuser2")

        self.loan1 = make_loan(
            user=self.user1,
            state=LoanState.ACTIVE,
            year=1402,
            month=6,
            amount=Decimal("100.00"),
        )
        self.loan2 = make_loan(
            user=self.user2,
            state=LoanState.ACTIVE,
            year=1402,
            month=7,
            amount=Decimal("200.00"),
        )

    def test_get_loan_detail_own_loan(self):
        response = client.get(
            f"/{self.loan1.id}",
            headers=auth_headers(self.user1),
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], str(self.loan1.id))
        self.assertEqual(data["user_id"], self.user1.id)

    def test_get_loan_detail_main_user_can_see_any_loan(self):
        response = client.get(
            f"/{self.loan2.id}",
            headers=auth_headers(self.main_user),
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], str(self.loan2.id))

    def test_get_loan_detail_regular_user_cannot_see_other_loan(self):
        """Regular user cannot see another user's loan."""
        response = client.get(
            f"/{self.loan2.id}",
            headers=auth_headers(self.user1),
        )
        self.assertEqual(response.status_code, 403)
        data = response.json()
        self.assertIn("detail", data)

    def test_get_loan_detail_not_found(self):
        nonexistent_id = str(uuid.uuid4())
        response = client.get(
            f"/{nonexistent_id}",
            headers=auth_headers(self.user1),
        )
        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertIn("detail", data)

    def test_get_loan_detail_invalid_uuid(self):
        response = client.get(
            "/not-a-valid-uuid",
            headers=auth_headers(self.user1),
        )
        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertIn("detail", data)

    def test_get_loan_detail_no_auth(self):
        response = client.get(f"/{self.loan1.id}")
        self.assertEqual(response.status_code, 401)

    def test_get_loan_detail_response_fields(self):
        response = client.get(
            f"/{self.loan1.id}",
            headers=auth_headers(self.user1),
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        expected_fields = [
            "id",
            "user_id",
            "username",
            "amount",
            "state",
            "jalali_year",
            "jalali_month",
            "min_amount_for_each_payment",
            "total_paid",
            "remaining_balance",
            "log",
            "payments",
        ]
        for field in expected_fields:
            self.assertIn(field, data)
