"""PayPal Sandbox REST client: OAuth2 + Payouts.

Sandbox base: https://api-m.sandbox.paypal.com
"""
from __future__ import annotations

import base64
import os

import httpx

for _k in ("no_proxy", "NO_PROXY"):
    _v = os.environ.get(_k, "")
    if "[" in _v:
        os.environ[_k] = ",".join(p for p in _v.split(",") if "[" not in p)


class PayPalError(Exception):
    def __init__(self, status: int, body):
        self.status = status
        self.body = body
        super().__init__(f"PayPal API HTTP {status}: {body}")


class PayPalClient:
    def __init__(self, base_url: str, client_id: str, client_secret: str,
                 timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        self._http = httpx.Client(timeout=timeout)
        self._token: str | None = None

    def _auth_header(self) -> str:
        raw = f"{self.client_id}:{self.client_secret}".encode()
        return "Basic " + base64.b64encode(raw).decode()

    def get_token(self) -> str:
        """OAuth2 client-credentials grant."""
        r = self._http.post(
            self.base_url + "/v1/oauth2/token",
            headers={"Authorization": self._auth_header(),
                     "Content-Type": "application/x-www-form-urlencoded"},
            content="grant_type=client_credentials",
        )
        body = r.json() if r.text else {}
        if not r.is_success:
            raise PayPalError(r.status_code, body)
        self._token = body["access_token"]
        return self._token

    def _headers(self) -> dict:
        if not self._token:
            self.get_token()
        return {"Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json"}

    def create_payout(self, recipient: str, amount: str, currency: str = "USD",
                      note: str = "", sender_batch_id: str | None = None) -> dict:
        """Single-item batch payout. Amount as decimal string, e.g. '25.00'.

        recipient: PayPal email of the payee (sandbox: use sandbox receiver).
        """
        import uuid
        payload = {
            "sender_batch_header": {
                "sender_batch_id": sender_batch_id or f"pp-{uuid.uuid4().hex[:12]}",
                "email_subject": "Payment from PayPilot",
            },
            "items": [{
                "recipient_type": "EMAIL",
                "amount": {"value": amount, "currency": currency},
                "receiver": recipient,
                "note": note or "Approved by PayPilot AI",
                "sender_item_id": f"item-{uuid.uuid4().hex[:8]}",
            }],
        }
        r = self._http.post(self.base_url + "/v1/payments/payouts",
                            headers=self._headers(), json=payload)
        body = r.json() if r.text else {}
        if r.status_code not in (201, 200):
            raise PayPalError(r.status_code, body)
        return body

    def get_payout(self, payout_batch_id: str) -> dict:
        r = self._http.get(
            self.base_url + f"/v1/payments/payouts/{payout_batch_id}",
            headers=self._headers())
        body = r.json() if r.text else {}
        if not r.is_success:
            raise PayPalError(r.status_code, body)
        return body
