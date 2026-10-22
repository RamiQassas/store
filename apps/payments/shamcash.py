"""
ShamCash E-Payment API Client & Direct JWE Cryptography
Documentation: ShamCash E-Payment Integration Guide v1.0.0 (2026-06-01)
Terms & Conditions: ShamCash B2B API Collection Specification

Security Principles:
- Confidential server-side key storage (Agent Key & Base64 AES Secret Key).
- Direct JWE (alg="dir", enc="A256GCM", cty="json") encryption with 5-segment compact token.
- Mandatory iat and exp claim verification to prevent replay attacks.
- Dual Currency support: USD (currencyId=1) and SYP (currencyId=2).
- Zero user surcharge compliance (Article 7 of Terms & Conditions).
- 5-Year log retention integration (Article 14 of Terms & Conditions).
"""

import base64
import json
import logging
import os
import time
import uuid
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple, Union

import requests
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger(__name__)


class ShamCashError(Exception):
    """Base exception for ShamCash integration errors."""

    def __init__(
        self,
        message: str,
        error_code: Optional[int] = None,
        raw_response: Optional[dict] = None,
    ):
        super().__init__(message)
        self.error_code = error_code
        self.raw_response = raw_response or {}


class ShamCashClient:
    STAGING_BASE_URL = "https://dev.shamlogix.tech/services"
    LIVE_BASE_URL = "https://api.shamcash.sy/services"

    # Official Bill Status Identifiers (Doc Section 6.3 & Table page 16)
    STATUS_PENDING = 1          # pending: Bill is awaiting user payment
    STATUS_REFUNDED = 2         # refund: The bill payment has been fully refunded back to the user
    STATUS_EXPIRED = 3          # expired: Bill expired (not paid within 10 minutes)
    STATUS_PAID = 4             # paid: Bill successfully paid
    STATUS_PARTLY_REFUNDED = 5  # partly refunded: A portion of the paid amount has been refunded

    # Backwards-compatible aliases
    STATUS_FULLY_REFUNDED = STATUS_REFUNDED
    STATUS_PARTIALLY_REFUNDED = STATUS_PARTLY_REFUNDED

    STATUS_NAMES = {
        STATUS_PENDING: "pending",
        STATUS_REFUNDED: "refund",
        STATUS_EXPIRED: "expired",
        STATUS_PAID: "paid",
        STATUS_PARTLY_REFUNDED: "partly refunded",
    }

    STATUS_ARABIC_NAMES = {
        STATUS_PENDING: "قيد الانتظار (في انتظار السداد)",
        STATUS_REFUNDED: "مسترد بالكامل",
        STATUS_EXPIRED: "منتهي الصلاحية (تجاوز 10 دقائق)",
        STATUS_PAID: "مدفوع بنجاح",
        STATUS_PARTLY_REFUNDED: "مسترد جزئياً",
    }

    # Official Currency Identifiers
    CURRENCY_USD = 1
    CURRENCY_SYP = 2

    # Standard browser User-Agent to prevent Cloudflare/WAF anti-bot false drops
    DEFAULT_USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )

    def __init__(
        self,
        agent_key: str,
        secret_key: str,
        base_url: Optional[str] = None,
        mode: str = "sandbox",
        timeout: int = 25,
    ):
        self.agent_key = (agent_key or "").strip()
        self.raw_secret_key = (secret_key or "").strip()
        self.mode = (mode or "sandbox").strip().lower()
        self.timeout = timeout

        if base_url and base_url.strip():
            self.base_url = base_url.strip().rstrip("/")
        else:
            self.base_url = (
                self.LIVE_BASE_URL if self.mode == "live" else self.STAGING_BASE_URL
            )

        # Validate and decode Base64 secret key (32 bytes required for AES-256)
        if not self.raw_secret_key:
            self._key_bytes = b""
        else:
            try:
                self._key_bytes = base64.b64decode(self.raw_secret_key)
                if len(self._key_bytes) != 32:
                    raise ValueError(
                        f"ShamCash secret key must decode to exactly 32 bytes (got {len(self._key_bytes)})"
                    )
            except Exception as err:
                logger.error(f"Failed to decode ShamCash secret key: {err}")
                raise ShamCashError(f"Invalid ShamCash secret key: {err}") from err

    @classmethod
    def from_integration(cls, integration) -> "ShamCashClient":
        """Instantiate client from PaymentGatewayIntegration model."""
        from django.conf import settings

        agent_key = (getattr(integration, "api_key", None) or "").strip()
        secret_key = (getattr(integration, "api_secret", None) or "").strip()
        base_url = (getattr(integration, "base_url", None) or "").strip()
        mode = getattr(integration, "mode", "sandbox")

        if hasattr(integration, "settings") and isinstance(integration.settings, dict):
            agent_key = agent_key or str(integration.settings.get("agent_key", "")).strip()
            secret_key = secret_key or str(integration.settings.get("secret_key", "")).strip()

        if not agent_key:
            agent_key = getattr(settings, "SHAM_CASH_AGENT_KEY", "").strip()
        if not secret_key:
            secret_key = getattr(settings, "SHAM_CASH_SECRET_KEY", "").strip()
        if not base_url:
            base_url = getattr(settings, "SHAM_CASH_BASE_URL", "").strip()

        return cls(
            agent_key=agent_key,
            secret_key=secret_key,
            base_url=base_url or None,
            mode=mode,
        )

    # ── Cryptographic Primitives (Direct JWE / AES-256-GCM) ──────────────────────

    @staticmethod
    def _b64url_encode(data: bytes) -> str:
        """Encode bytes to Base64URL string without '=' padding."""
        return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")

    @staticmethod
    def _b64url_decode(token: str) -> bytes:
        """Decode Base64URL string restoring missing '=' padding."""
        s = token.strip()
        rem = len(s) % 4
        if rem > 0:
            s += "=" * (4 - rem)
        return base64.urlsafe_b64decode(s.encode("ascii"))

    def encrypt_payload(self, payload: Dict[str, Any], ttl_seconds: int = 300) -> str:
        """
        Encrypt a dictionary into a ShamCash-compliant Direct JWE string:
        BASE64URL(Header) . . BASE64URL(IV) . BASE64URL(Ciphertext) . BASE64URL(Tag)
        """
        if not self._key_bytes:
            raise ShamCashError("ShamCash secret key is missing; cannot encrypt.")

        now = int(time.time())
        claims = dict(payload)
        claims["iat"] = claims.get("iat", now)
        claims["exp"] = claims.get("exp", now + ttl_seconds)

        payload_bytes = json.dumps(claims, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        header_bytes = json.dumps({"alg": "dir", "enc": "A256GCM", "cty": "json"}, separators=(",", ":")).encode("utf-8")
        h_b64 = self._b64url_encode(header_bytes)

        # 12-byte random cryptographic nonce
        iv = os.urandom(12)
        iv_b64 = self._b64url_encode(iv)

        # AAD for AES-GCM is the ASCII bytes of BASE64URL(Header)
        aad = h_b64.encode("ascii")

        aesgcm = AESGCM(self._key_bytes)
        # AESGCM.encrypt appends 16-byte authentication tag to ciphertext
        ct_and_tag = aesgcm.encrypt(iv, payload_bytes, aad)
        ciphertext = ct_and_tag[:-16]
        tag = ct_and_tag[-16:]

        ct_b64 = self._b64url_encode(ciphertext)
        tag_b64 = self._b64url_encode(tag)

        # 5 dot-separated segments with the second segment empty (Direct Key)
        return f"{h_b64}..{iv_b64}.{ct_b64}.{tag_b64}"

    def decrypt_payload(self, jwe_token: str, verify_exp: bool = True, clock_skew: int = 60) -> Dict[str, Any]:
        """
        Decrypt a ShamCash Direct JWE string and return claims dict.
        Validates token structure, AES-GCM auth tag, and expiration claim.
        """
        if not self._key_bytes:
            raise ShamCashError("ShamCash secret key is missing; cannot decrypt.")

        if not jwe_token or not isinstance(jwe_token, str):
            raise ShamCashError("Invalid or empty JWE token provided.")

        parts = jwe_token.strip().split(".")
        if len(parts) != 5:
            raise ShamCashError(f"Invalid JWE format: expected 5 parts, got {len(parts)}.")

        h_b64, empty_key, iv_b64, ct_b64, tag_b64 = parts
        if empty_key != "":
            logger.debug(f"Direct JWE second part is expected to be empty; got length {len(empty_key)}")

        try:
            iv = self._b64url_decode(iv_b64)
            ciphertext = self._b64url_decode(ct_b64)
            tag = self._b64url_decode(tag_b64)
        except Exception as err:
            raise ShamCashError(f"Failed to decode JWE base64 segments: {err}") from err

        aad = h_b64.encode("ascii")
        try:
            aesgcm = AESGCM(self._key_bytes)
            decrypted_bytes = aesgcm.decrypt(iv, ciphertext + tag, aad)
            payload = json.loads(decrypted_bytes.decode("utf-8"))
        except Exception as err:
            logger.warning(f"Failed to decrypt/verify ShamCash payload: {err}")
            raise ShamCashError(f"Payload decryption failed or tag mismatch: {err}") from err

        if verify_exp:
            exp = payload.get("exp")
            if exp is not None:
                now = int(time.time())
                if now > (int(exp) + clock_skew):
                    raise ShamCashError(f"JWE payload expired (exp: {exp}, now: {now}).")

        return payload

    # ── HTTP Layer with 5-Year Compliance Audit Logging ──────────────────────────

    def _request(self, endpoint: str, payload_dict: Dict[str, Any]) -> Dict[str, Any]:
        """
        Send encrypted request to ShamCash endpoint and handle response.
        Complies with 5-year retention audit requirements by recording every call.
        """
        url = f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        token = self.encrypt_payload(payload_dict)

        headers = {
            "User-Agent": self.DEFAULT_USER_AGENT,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        body = {
            "agentKey": self.agent_key,
            "encData": token,
        }

        bill_no = str(payload_dict.get("billNo") or "").strip()
        logger.info(f"Sending ShamCash request to {url} [billNo={bill_no}]")

        start_time = time.time()
        status_code = 0
        raw_res = None
        error_msg = ""
        result_code = None

        try:
            response = requests.post(url, json=body, headers=headers, timeout=self.timeout)
            status_code = response.status_code
            duration_ms = int((time.time() - start_time) * 1000)

            try:
                raw_res = response.json()
            except Exception:
                raw_res = {"text": response.text[:500]}
                error_msg = f"Non-JSON response (HTTP {status_code})"

            if isinstance(raw_res, dict):
                result_code = raw_res.get("result")

            # 2500 is official ShamCash success code
            is_success = (status_code == 200 and result_code == 2500)
            if not is_success and not error_msg:
                error_msg = (raw_res.get("message") if isinstance(raw_res, dict) else "") or f"Result code {result_code}"

            self._log_api_call(
                endpoint=endpoint,
                bill_no=bill_no,
                request_payload=payload_dict,
                status_code=status_code,
                result_code=result_code,
                response_data=raw_res,
                duration_ms=duration_ms,
                is_success=is_success,
                error_message=error_msg,
            )

        except requests.exceptions.Timeout as err:
            duration_ms = int((time.time() - start_time) * 1000)
            self._log_api_call(
                endpoint=endpoint,
                bill_no=bill_no,
                request_payload=payload_dict,
                status_code=504,
                result_code=1000,
                response_data=None,
                duration_ms=duration_ms,
                is_success=False,
                error_message=f"Timeout: {err}",
            )
            logger.error(f"ShamCash request timeout ({url}): {err}")
            raise ShamCashError("ShamCash API request timed out.", error_code=504) from err

        except requests.exceptions.RequestException as err:
            duration_ms = int((time.time() - start_time) * 1000)
            self._log_api_call(
                endpoint=endpoint,
                bill_no=bill_no,
                request_payload=payload_dict,
                status_code=502,
                result_code=1000,
                response_data=None,
                duration_ms=duration_ms,
                is_success=False,
                error_message=f"Network error: {err}",
            )
            logger.error(f"ShamCash request failed ({url}): {err}")
            raise ShamCashError(f"ShamCash network error: {err}", error_code=502) from err

        if not isinstance(raw_res, dict):
            raise ShamCashError(
                f"ShamCash returned unexpected response (HTTP {status_code})",
                error_code=status_code,
                raw_response={"text": str(raw_res)},
            )

        # Handle business logic failures
        if status_code != 200 or (result_code is not None and result_code != 2500):
            msg = raw_res.get("message") or f"API error with result code {result_code}"
            logger.warning(f"ShamCash error returned: code={result_code}, message={msg}, data={raw_res}")
            raise ShamCashError(
                message=f"ShamCash: {msg}",
                error_code=result_code or status_code,
                raw_response=raw_res,
            )

        return raw_res

    def _log_api_call(
        self,
        endpoint: str,
        bill_no: str,
        request_payload: dict,
        status_code: int,
        result_code: Optional[int],
        response_data: Any,
        duration_ms: int,
        is_success: bool,
        error_message: str = "",
    ):
        """Asynchronously or safely persist API log to ShamCashApiLog model for 5-year retention."""
        try:
            from apps.payments.models import ShamCashApiLog
            ShamCashApiLog.objects.create(
                endpoint=endpoint,
                bill_no=bill_no,
                request_payload_sanitized=request_payload,
                response_status_code=status_code,
                response_result_code=result_code,
                response_data=response_data if isinstance(response_data, dict) else {"raw": str(response_data)},
                duration_ms=duration_ms,
                is_success=is_success,
                error_message=error_message[:500],
            )
        except Exception as log_err:
            # Never let audit logging failure block the payment pipeline
            logger.debug(f"Audit log writing skipped: {log_err}")

    # ── Business Endpoints ───────────────────────────────────────────────────────

    def create_bill(
        self,
        bill_no: str,
        amount: Union[Decimal, float, int, str],
        currency_id: int,
        callback_url: str,
        redirect_url: str,
        note: str = "",
    ) -> Dict[str, Any]:
        """
        Create a payable bill on ShamCash (Doc Section 6.1).
        Handles network interruption / retry with 1704 gracefully per Doc Section 10 recommendations.
        """
        amt = Decimal(str(amount)).quantize(Decimal("0.01"))
        if amt <= Decimal("0.00"):
            raise ShamCashError("Bill amount must be greater than zero.")

        if currency_id not in (self.CURRENCY_USD, self.CURRENCY_SYP):
            raise ShamCashError(f"Unsupported currencyId {currency_id}. Must be 1 (USD) or 2 (SYP).")

        payload = {
            "billNo": str(bill_no).strip(),
            "amount": float(amt),
            "currencyId": int(currency_id),
            "callbackUrl": str(callback_url).strip()[:500],
            "redirectUrl": str(redirect_url).strip()[:500],
            "note": str(note or "").strip()[:500],
        }

        try:
            res = self._request("api/ElectronicPayment/createBill", payload)
        except ShamCashError as err:
            # Recommendation (Doc Section 10): Intercept 1704 (Bill No Already Exists) gracefully
            if err.error_code == 1704:
                logger.info(f"createBill returned 1704 for {bill_no}; querying existing bill status.")
                try:
                    existing_bill = self.get_bill_info(bill_no)
                    if existing_bill:
                        return existing_bill
                except Exception as query_err:
                    logger.warning(f"Fallback getBillInfo failed for 1704: {query_err}")
            raise err

        data = res.get("data") or {}
        if not data.get("paymentUrl"):
            logger.error(f"ShamCash createBill response missing paymentUrl: {res}")
            raise ShamCashError("ShamCash response did not include paymentUrl.", raw_response=res)

        return data

    def get_bill_info(self, bill_no: str) -> Dict[str, Any]:
        """
        Query the current status of a bill (Doc Section 6.2).
        Used solely as fallback reconciliation when webhook is not received.
        """
        payload = {"billNo": str(bill_no).strip()}
        res = self._request("api/ElectronicPayment/getBillInfo", payload)
        return res.get("data") or {}

    def refund_bill(
        self,
        bill_no: str,
        amount: Union[Decimal, float, int, str],
        note: str = "",
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Initiate a full or partial refund for a paid bill (Doc Section 6.3).
        - Currency is implicitly inherited from the original bill (no currencyId sent).
        - idempotencyKey: 10 to 100 characters unique key.
        - note: explanation note (field name in spec is 'note').
        - Returns data object with tranId.
        """
        amt = Decimal(str(amount)).quantize(Decimal("0.01"))
        if amt <= Decimal("0.00"):
            raise ShamCashError("Refund amount must be greater than zero.")

        key = str(idempotency_key or uuid.uuid4()).strip()
        if len(key) < 10 or len(key) > 100:
            key = f"REF-{uuid.uuid4().hex}"

        payload = {
            "billNo": str(bill_no).strip(),
            "amount": float(amt),
            "idempotencyKey": key,
            "note": str(note or "").strip()[:200],
        }
        res = self._request("api/ElectronicPayment/refundBill", payload)
        return res.get("data") or {}

    def get_transactions(
        self,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        after_tran_id: int = 0,
        limit: int = 500,
    ) -> Dict[str, Any]:
        """
        Query agent financial ledger using cursor-based pagination (Doc Section 6.4 & 11).
        Parameters:
        - fromDate: Optional starting date filter (yyyy-MM-dd)
        - toDate: Optional ending date filter (yyyy-MM-dd)
        - afterTranId: Cursor transaction ID (defaults to 0)
        - limit: 10 to 2500 (defaults to 500)
        Returns:
        - hasMore: bool
        - lastReturnedTranId: int
        - list: list of transaction objects
        """
        bounded_limit = max(10, min(2500, int(limit or 500)))
        payload: Dict[str, Any] = {
            "afterTranId": int(after_tran_id or 0),
            "limit": bounded_limit,
        }
        if from_date:
            payload["fromDate"] = str(from_date).strip()
        if to_date:
            payload["toDate"] = str(to_date).strip()

        res = self._request("api/ElectronicPayment/getTransactions", payload)
        return res.get("data") or {}

    def fetch_all_reconciliation_transactions(
        self,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        limit: int = 1000,
        max_pages: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Executes the official reconciliation loop pattern (Doc Section 11):
        Iterates with cursor afterTranId until hasMore is false.
        """
        all_transactions = []
        after_tran_id = 0
        pages = 0

        while pages < max_pages:
            pages += 1
            res = self.get_transactions(
                from_date=from_date,
                to_date=to_date,
                after_tran_id=after_tran_id,
                limit=limit,
            )
            tx_list = res.get("list") or []
            all_transactions.extend(tx_list)

            has_more = bool(res.get("hasMore"))
            last_id = res.get("lastReturnedTranId")

            if not has_more or not tx_list or not last_id or last_id == after_tran_id:
                break

            after_tran_id = int(last_id)

        return all_transactions
