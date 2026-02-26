"""
End-to-end API tests for the Users API.

Tests cover:
- POST /api/auth/login
- POST /api/auth/users
- GET /api/auth/users
- GET /api/auth/me
- PATCH /api/auth/me/loan-request
"""

from decimal import Decimal
from django.test import TestCase

from ninja.testing import TestClient

from apps.users.api import router
from apps.common.auth import create_access_token


client = TestClient(router)


def auth_headers(user) -> dict:
    """Return Authorization headers for the given user."""
    token = create_access_token(user.id)
    return {"Authorization": f"Bearer {token}"}


class TestLogin(TestCase):
    """Tests for POST /login"""

    def setUp(self):
        from apps.users.models import User

        self.user = User.objects.create_user(
            username="loginuser",
            password="securepass123",
            email="login@example.com",
            is_main=False,
        )
        self.main_user = User.objects.create_user(
            username="loginadmin",
            password="adminpass123",
            email="loginadmin@example.com",
            is_main=True,
        )

    def test_login_success_regular_user(self):
        response = client.post(
            "/login",
            json={"username": "loginuser", "password": "securepass123"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("access_token", data)
        self.assertEqual(data["username"], "loginuser")
        self.assertFalse(data["is_main"])
        self.assertEqual(data["token_type"], "bearer")

    def test_login_success_main_user(self):
        response = client.post(
            "/login",
            json={"username": "loginadmin", "password": "adminpass123"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["is_main"])

    def test_login_wrong_password(self):
        response = client.post(
            "/login",
            json={"username": "loginuser", "password": "wrongpassword"},
        )
        self.assertEqual(response.status_code, 401)
        data = response.json()
        self.assertIn("detail", data)

    def test_login_nonexistent_user(self):
        response = client.post(
            "/login",
            json={"username": "doesnotexist", "password": "somepassword"},
        )
        self.assertEqual(response.status_code, 401)
        data = response.json()
        self.assertIn("detail", data)

    def test_login_missing_fields(self):
        response = client.post("/login", json={"username": "loginuser"})
        self.assertEqual(response.status_code, 422)

    def test_login_empty_body(self):
        response = client.post("/login", json={})
        self.assertEqual(response.status_code, 422)


class TestCreateUser(TestCase):
    """Tests for POST /users"""

    def setUp(self):
        from apps.users.models import User

        self.main_user = User.objects.create_user(
            username="createadmin",
            password="adminpass123",
            email="createadmin@example.com",
            is_main=True,
        )
        self.regular_user = User.objects.create_user(
            username="createregular",
            password="regularpass123",
            email="createregular@example.com",
            is_main=False,
        )

    def test_create_user_as_main_user(self):
        response = client.post(
            "/users",
            json={
                "username": "newmember",
                "password": "newpass123",
                "first_name": "New",
                "last_name": "Member",
                "email": "newmember@example.com",
                "is_main": False,
                "loan_request_amount": "50.00",
            },
            headers=auth_headers(self.main_user),
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["username"], "newmember")
        self.assertEqual(data["first_name"], "New")
        self.assertEqual(data["last_name"], "Member")
        self.assertFalse(data["is_main"])

    def test_create_user_duplicate_username(self):
        # First creation
        client.post(
            "/users",
            json={"username": "dupuser", "password": "duppass123"},
            headers=auth_headers(self.main_user),
        )
        # Second creation with same username
        response = client.post(
            "/users",
            json={"username": "dupuser", "password": "duppass456"},
            headers=auth_headers(self.main_user),
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("detail", data)

    def test_create_user_unauthorized_regular_user(self):
        response = client.post(
            "/users",
            json={"username": "shouldfail", "password": "failpass123"},
            headers=auth_headers(self.regular_user),
        )
        self.assertEqual(response.status_code, 401)

    def test_create_user_no_auth(self):
        response = client.post(
            "/users",
            json={"username": "nonauthuser", "password": "nonauthpass123"},
        )
        self.assertEqual(response.status_code, 401)

    def test_create_user_missing_required_fields(self):
        response = client.post(
            "/users",
            json={"username": "onlyusername"},
            headers=auth_headers(self.main_user),
        )
        self.assertEqual(response.status_code, 422)

    def test_create_user_short_username(self):
        response = client.post(
            "/users",
            json={"username": "ab", "password": "validpass123"},
            headers=auth_headers(self.main_user),
        )
        self.assertEqual(response.status_code, 422)

    def test_create_user_short_password(self):
        response = client.post(
            "/users",
            json={"username": "validuser", "password": "short"},
            headers=auth_headers(self.main_user),
        )
        self.assertEqual(response.status_code, 422)


class TestListUsers(TestCase):
    """Tests for GET /users"""

    def setUp(self):
        from apps.users.models import User

        self.main_user = User.objects.create_user(
            username="listadmin",
            password="adminpass123",
            email="listadmin@example.com",
            is_main=True,
        )
        self.regular_user = User.objects.create_user(
            username="listregular",
            password="regularpass123",
            email="listregular@example.com",
            is_main=False,
        )

    def test_list_users_as_main_user(self):
        response = client.get(
            "/users",
            headers=auth_headers(self.main_user),
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertGreaterEqual(len(data), 2)
        usernames = [u["username"] for u in data]
        self.assertIn("listadmin", usernames)
        self.assertIn("listregular", usernames)

    def test_list_users_unauthorized_regular_user(self):
        response = client.get(
            "/users",
            headers=auth_headers(self.regular_user),
        )
        self.assertEqual(response.status_code, 401)

    def test_list_users_no_auth(self):
        response = client.get("/users")
        self.assertEqual(response.status_code, 401)

    def test_list_users_response_fields(self):
        response = client.get(
            "/users",
            headers=auth_headers(self.main_user),
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertGreater(len(data), 0)
        user_data = data[0]
        expected_fields = [
            "id",
            "username",
            "first_name",
            "last_name",
            "email",
            "is_main",
            "balance",
            "loan_request_amount",
            "has_active_loan",
        ]
        for field in expected_fields:
            self.assertIn(field, user_data)


class TestGetMe(TestCase):
    """Tests for GET /me"""

    def setUp(self):
        from apps.users.models import User

        self.user = User.objects.create_user(
            username="meuser",
            password="mepass123",
            email="meuser@example.com",
            first_name="Me",
            last_name="User",
            is_main=False,
            balance=Decimal("100.00"),
            loan_request_amount=Decimal("50.00"),
        )

    def test_get_me_authenticated(self):
        response = client.get(
            "/me",
            headers=auth_headers(self.user),
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["username"], "meuser")
        self.assertEqual(data["first_name"], "Me")
        self.assertEqual(data["last_name"], "User")
        self.assertEqual(data["email"], "meuser@example.com")
        self.assertFalse(data["is_main"])
        self.assertFalse(data["has_active_loan"])

    def test_get_me_no_auth(self):
        response = client.get("/me")
        self.assertEqual(response.status_code, 401)

    def test_get_me_invalid_token(self):
        response = client.get(
            "/me",
            headers={"Authorization": "Bearer invalidtoken"},
        )
        self.assertEqual(response.status_code, 401)

    def test_get_me_response_fields(self):
        response = client.get(
            "/me",
            headers=auth_headers(self.user),
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        expected_fields = [
            "id",
            "username",
            "first_name",
            "last_name",
            "email",
            "is_main",
            "balance",
            "loan_request_amount",
            "has_active_loan",
        ]
        for field in expected_fields:
            self.assertIn(field, data)


class TestUpdateLoanRequestAmount(TestCase):
    """Tests for PATCH /me/loan-request"""

    def setUp(self):
        from apps.users.models import User

        self.user = User.objects.create_user(
            username="loanrequser",
            password="loanreqpass123",
            email="loanreq@example.com",
            is_main=False,
            loan_request_amount=Decimal("50.00"),
        )

    def test_update_loan_request_amount_success(self):
        response = client.patch(
            "/me/loan-request",
            json={"loan_request_amount": "100.00"},
            headers=auth_headers(self.user),
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(
            Decimal(data["loan_request_amount"]), Decimal("100.00")
        )

    def test_update_loan_request_amount_to_zero(self):
        """Setting to 0 opts out of loan assignment."""
        response = client.patch(
            "/me/loan-request",
            json={"loan_request_amount": "0"},
            headers=auth_headers(self.user),
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(Decimal(data["loan_request_amount"]), Decimal("0"))

    def test_update_loan_request_amount_no_auth(self):
        response = client.patch(
            "/me/loan-request",
            json={"loan_request_amount": "100.00"},
        )
        self.assertEqual(response.status_code, 401)

    def test_update_loan_request_amount_negative_value(self):
        """Negative loan_request_amount should be rejected."""
        response = client.patch(
            "/me/loan-request",
            json={"loan_request_amount": "-10.00"},
            headers=auth_headers(self.user),
        )
        self.assertEqual(response.status_code, 422)

    def test_update_loan_request_amount_missing_field(self):
        response = client.patch(
            "/me/loan-request",
            json={},
            headers=auth_headers(self.user),
        )
        self.assertEqual(response.status_code, 422)

    def test_update_loan_request_amount_persists(self):
        """Verify the update is actually saved to the database."""

        client.patch(
            "/me/loan-request",
            json={"loan_request_amount": "75.50"},
            headers=auth_headers(self.user),
        )
        self.user.refresh_from_db()
        self.assertEqual(self.user.loan_request_amount, Decimal("75.50"))
