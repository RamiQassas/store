"""
Paymera eGate v4.0 API Client
Documentation: Paymera eGate API Specification v4.0 (2026-07-05)
"""

import base64
import logging
from decimal import Decimal
from typing import Any, Dict, Optional

import requests
from requests.auth import HTTPBasicAuth

logger = logging.getLogger(__name__)


class PaymeraError(Exception):
    """Base exception for Paymera integration errors."""
    def __init__(self, message: str, error_code: Optional[int] = None, raw_response: Optional[dict] = None):
        super().__init__(message)
        self.error_code = error_code
        self.raw_response = raw_response or {}


class PaymeraClient:
    SANDBOX_BASE_URL = "https://egate-t.paymera.cc"
    LIVE_BASE_URL = "https://egate.paymera.cc"

    # Status constants
    STATUS_PENDING = "P"
    STATUS_ACCEPTED = "A"
    STATUS_FAILED = "F"
    STATUS_CANCELED = "C"

    def __init__(
        self,
        api_key: str,
        terminal_id: str,
        base_url: Optional[str] = None,
        mode: str = "sandbox",
        timeout: int = 30,
    ):
        self.api_key = (api_key or "").strip()
        self.terminal_id = (terminal_id or "").strip()
        self.timeout = timeout
        self.mode = mode

        if base_url and base_url.strip():
            self.base_url = base_url.strip().rstrip("/")
        else:
            self.base_url = self.LIVE_BASE_URL if mode == "live" else self.SANDBOX_BASE_URL

    @classmethod
    def from_integration(cls, integration) -> "PaymeraClient":
        """Instantiate client from PaymentGatewayIntegration model."""
        terminal_id = integration.terminal_id
        if not terminal_id and isinstance(integration.settings, dict):
            terminal_id = integration.settings.get("terminal_id", "")

        return cls(
            api_key=integration.api_key,
            terminal_id=terminal_id,
            base_url=integration.base_url,
            mode=integration.mode,
        )

    def _get_headers(self) -> Dict[str, str]:
        # Basic Auth: api_key as username, empty password with trailing colon
        auth_bytes = f"{self.api_key}:".encode("utf-8")
        auth_b64 = base64.b64encode(auth_bytes).decode("ascii")
        return {
            "Authorization": f"Basic {auth_b64}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def create_payment(
        self,
        amount: int | float | Decimal,
        callback_url: str,
        trigger_url: str,
        lang: str = "ar",
        notes: str = "",
        saved_cards: bool = False,
        app_user: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create payment session.
        Endpoint: POST /api/create-payment
        Paymera expects amount as integer in Syrian Liras without decimals or commas.
        """
        if not self.api_key:
            raise PaymeraError("Paymera API Key is not configured.")
        if not self.terminal_id:
            raise PaymeraError("Paymera Terminal ID is not configured.")

        # Ensure amount is clean integer without decimals
        int_amount = int(round(float(amount)))
        if int_amount <= 0:
            raise PaymeraError(f"Invalid payment amount: {int_amount}")

        url = f"{self.base_url}/api/create-payment"
        payload = {
            "lang": lang if lang in ("ar", "en") else "ar",
            "terminalId": str(self.terminal_id),
            "amount": int_amount,
            "callbackURL": callback_url,
            "triggerURL": trigger_url,
            "savedCards": "1" if saved_cards else "0",
            "notes": str(notes)[:250] if notes else "",
        }
        if saved_cards and app_user:
            payload["appUser"] = str(app_user)

        logger.info(f"Paymera create_payment request to {url} with amount={int_amount}, terminal={self.terminal_id}")

        try:
            resp = requests.post(url, json=payload, headers=self._get_headers(), timeout=self.timeout)
        except requests.RequestException as exc:
            logger.error(f"Paymera network error calling create-payment: {exc}")
            raise PaymeraError(f"Failed to connect to Paymera: {exc}") from exc

        try:
            data = resp.json()
        except ValueError:
            logger.error(f"Paymera returned non-JSON response ({resp.status_code}): {resp.text}")
            raise PaymeraError(f"Paymera invalid response (HTTP {resp.status_code})")

        error_code = data.get("ErrorCode")
        error_msg = data.get("ErrorMessage", "Unknown response")

        if error_code != 0:
            logger.error(f"Paymera create-payment failed with code {error_code}: {error_msg}")
            raise PaymeraError(f"Paymera error ({error_code}): {error_msg}", error_code=error_code, raw_response=data)

        payload_data = data.get("Data") or {}
        payment_id = payload_data.get("paymentId")
        redirect_url = payload_data.get("url")

        if not payment_id or not redirect_url:
            logger.error(f"Paymera response missing paymentId or url: {data}")
            raise PaymeraError("Paymera response missing paymentId or redirect url", raw_response=data)

        logger.info(f"Paymera payment created successfully. payment_id={payment_id}")
        return {
            "payment_id": payment_id,
            "url": redirect_url,
            "raw": data,
        }

    def get_payment_status(self, payment_id: str) -> Dict[str, Any]:
        """
        Check payment status.
        Endpoint: GET /api/get-payment-status/{payment_id}
        """
        if not payment_id:
            raise PaymeraError("payment_id is required.")

        clean_payment_id = str(payment_id).strip()
        url = f"{self.base_url}/api/get-payment-status/{clean_payment_id}"

        logger.info(f"Paymera checking payment status: {url}")
        try:
            resp = requests.get(url, headers=self._get_headers(), timeout=self.timeout)
        except requests.RequestException as exc:
            logger.error(f"Paymera network error checking payment status: {exc}")
            raise PaymeraError(f"Failed to connect to Paymera: {exc}") from exc

        try:
            data = resp.json()
        except ValueError:
            logger.error(f"Paymera non-JSON response ({resp.status_code}): {resp.text}")
            raise PaymeraError(f"Paymera invalid response (HTTP {resp.status_code})")

        error_code = data.get("ErrorCode")
        error_msg = data.get("ErrorMessage", "")

        if error_code != 0:
            logger.warning(f"Paymera get-payment-status returned error ({error_code}): {error_msg}")
            raise PaymeraError(f"Paymera error ({error_code}): {error_msg}", error_code=error_code, raw_response=data)

        payload_data = data.get("Data") or {}
        return {
            "status": payload_data.get("status"),  # P, A, F, C
            "rrn": payload_data.get("rrn"),
            "amount": payload_data.get("amount"),
            "terminal_id": payload_data.get("terminalId"),
            "timestamp": payload_data.get("creationTimestamp"),
            "notes": payload_data.get("notes"),
            "raw": data,
        }

    def cancel_payment(self, payment_id: str, lang: str = "ar") -> Dict[str, Any]:
        """
        Cancel / Reversal payment.
        Endpoint: POST /api/cancel-payment
        """
        if not payment_id:
            raise PaymeraError("payment_id is required for cancellation.")

        url = f"{self.base_url}/api/cancel-payment"
        payload = {
            "lang": lang if lang in ("ar", "en") else "ar",
            "payment_id": str(payment_id).strip(),
        }

        logger.info(f"Paymera canceling payment {payment_id}")
        try:
            resp = requests.post(url, json=payload, headers=self._get_headers(), timeout=self.timeout)
            data = resp.json()
        except Exception as exc:
            logger.error(f"Paymera cancel error: {exc}")
            raise PaymeraError(f"Paymera cancellation failed: {exc}") from exc

        return data
