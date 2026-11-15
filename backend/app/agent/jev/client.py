"""Low-level HTTP client for Jev (TypeSafe).

Request/response shape follows the example in jev-uw-team-plan.md, which is
itself marked UNCONFIRMED there pending a real API key — exact field names
must be checked against TypeSafe's docs once we have one. Keep this file as
the single place that would need to change if the shape differs.
"""

from __future__ import annotations

import os
import time

import httpx

from .models import Question

JEV_MODEL_DEFAULT = "jev-latest"


class JevUnavailableError(Exception):
    """Raised after retries are exhausted or on a non-retryable error."""


class JevClient:
    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str = JEV_MODEL_DEFAULT,
        timeout_s: float = 10.0,
        max_retries: int = 2,
        backoff_base_s: float = 0.5,
    ) -> None:
        self.base_url = base_url or os.environ.get("JEV_API_BASE_URL", "https://api.typesafe.ai")
        self.api_key = api_key or os.environ.get("JEV_API_KEY")
        self.model = model
        self.timeout_s = timeout_s
        self.max_retries = max_retries
        self.backoff_base_s = backoff_base_s

    def decide_raw(self, state: str | dict, questions: dict[str, Question]) -> dict:
        """POST a state + named questions to Jev, return the raw JSON response.

        Raises JevUnavailableError if the key is missing, or after retries
        are exhausted on timeouts/5xx/429. Does not retry on 4xx other than
        429 (treated as a bad request, not a transient failure).
        """
        if not self.api_key:
            raise JevUnavailableError("JEV_API_KEY is not set")

        payload = {
            "model": self.model,
            "state": state,
            "questions": {name: q.model_dump(exclude_none=True) for name, q in questions.items()},
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}

        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = httpx.post(
                    f"{self.base_url}/v1/decide",
                    json=payload,
                    headers=headers,
                    timeout=self.timeout_s,
                )
                if resp.status_code == 429 or resp.status_code >= 500:
                    last_exc = JevUnavailableError(f"Jev returned {resp.status_code}")
                else:
                    resp.raise_for_status()
                    return resp.json()
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_exc = exc

            if attempt < self.max_retries:
                time.sleep(self.backoff_base_s * (2**attempt))

        raise JevUnavailableError(str(last_exc)) from last_exc
