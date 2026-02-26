import httpx
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel


class BitpinPaymentInfo(BaseModel):
    """Parsed payment info from Bitpin API response."""

    payment_id: str
    amount: Decimal
    status: str  # e.g. "completed", "pending", "failed"
    currency: str  # e.g. "USDT"


class BitpinClient:
    """
    Client for verifying payments via the Bitpin exchange API.

    Bitpin payment verification endpoint:
    GET /v1/mch/payments/{payment_id}/

    The response contains the payment amount and status.
    We verify that the total payment amount in our system
    does not exceed the amount confirmed by Bitpin.
    """

    def __init__(self, base_url: str, api_key: Optional[str] = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.headers: dict[str, str] = {"Content-Type": "application/json"}
        if api_key:
            self.headers["Authorization"] = f"Token {api_key}"

    def get_payment(self, payment_id: str) -> Optional[BitpinPaymentInfo]:
        """
        Fetch payment details from Bitpin.
        Returns None if the payment is not found or request fails.
        """
        url = f"{self.base_url}/v1/mch/payments/{payment_id}/"
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(url, headers=self.headers)
                response.raise_for_status()
                data = response.json()
                return BitpinPaymentInfo(
                    payment_id=str(data.get("id", payment_id)),
                    amount=Decimal(str(data.get("amount", "0"))),
                    status=data.get("status", "unknown"),
                    currency=data.get("currency", "USDT"),
                )
        except (httpx.HTTPError, KeyError, ValueError, Exception):
            return None

    def verify_payment_amount(
        self, payment_id: str, expected_amount: Decimal
    ) -> tuple[bool, str]:
        """
        Verify that the Bitpin payment covers the expected amount.

        Returns:
            (True, "") if valid
            (False, reason) if invalid
        """
        info = self.get_payment(payment_id)
        if info is None:
            return False, f"Payment {payment_id} not found in Bitpin"
        if info.status not in ("completed", "paid", "confirmed", "done"):
            return (
                False,
                f"Payment {payment_id} status is '{info.status}', not completed",
            )
        if info.amount < expected_amount:
            return False, (
                f"Bitpin payment amount {info.amount} is less than "
                f"required {expected_amount}"
            )
        return True, ""


def get_bitpin_client() -> BitpinClient:
    """Factory function to create a BitpinClient from app settings."""
    from saghat.settings.base import settings as app_settings

    return BitpinClient(
        base_url=app_settings.BITPIN_API_BASE_URL,
        api_key=app_settings.BITPIN_API_KEY,
    )
