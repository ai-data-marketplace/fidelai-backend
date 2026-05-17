from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib import error, parse, request

from django.conf import settings


class ChapaClientError(RuntimeError):
    pass


@dataclass(slots=True)
class ChapaClient:
    secret_key: str | None = None
    base_url: str | None = None
    timeout: int = 30

    def __post_init__(self) -> None:
        self.secret_key = self.secret_key or getattr(settings, "CHAPA_SECRET_KEY", "")
        self.base_url = (self.base_url or getattr(settings, "CHAPA_BASE_URL", "https://api.chapa.co/v1")).rstrip("/")
        if not self.secret_key:
            raise ChapaClientError("CHAPA_SECRET_KEY is not configured")

    def initialize_transaction(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/transaction/initialize", payload)

    def verify_transaction(self, tx_ref: str) -> dict[str, Any]:
        safe_tx_ref = parse.quote(str(tx_ref), safe="")
        return self._request("GET", f"/transaction/verify/{safe_tx_ref}")

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        headers = {
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = request.Request(url=url, data=data, headers=headers, method=method)

        try:
            with request.urlopen(req, timeout=self.timeout) as response:
                body = response.read().decode("utf-8")
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise ChapaClientError(f"Chapa request failed with HTTP {exc.code}: {detail}") from exc
        except error.URLError as exc:
            raise ChapaClientError(f"Chapa request failed: {exc.reason}") from exc

        try:
            return json.loads(body) if body else {}
        except json.JSONDecodeError as exc:
            raise ChapaClientError("Chapa returned invalid JSON") from exc
