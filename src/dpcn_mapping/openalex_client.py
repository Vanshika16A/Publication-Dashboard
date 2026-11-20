"""Small OpenAlex API client with retry, budget tracking and an optional API key.

The API key is read from the OPENALEX_API_KEY environment variable or from a
`.env` file at the repository root (`.env` is gitignored). Without a key the
OpenAlex free tier allows roughly 1000 list requests per day.
"""

from __future__ import annotations

import os
import time
from typing import Any, Iterator

import requests

from .config import ROOT

BASE_URL = "https://api.openalex.org"
MAILTO = "gracy.garg@students.iiit.ac.in"


class BudgetExhausted(RuntimeError):
    """Raised when OpenAlex reports that the daily request budget is used up."""


def _api_key() -> str | None:
    key = os.environ.get("OPENALEX_API_KEY")
    if key:
        return key.strip()
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("OPENALEX_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


class OpenAlexClient:
    def __init__(self, min_interval: float = 0.12, max_retries: int = 6) -> None:
        self.session = requests.Session()
        self.session.headers["User-Agent"] = f"DPCN-Group16/1.0 (mailto:{MAILTO})"
        self.api_key = _api_key()
        self.min_interval = min_interval
        self.max_retries = max_retries
        self.requests_made = 0
        self.remaining: str | None = None
        self._last_call = 0.0

    def get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        params = {**params, "mailto": MAILTO}
        if self.api_key:
            params["api_key"] = self.api_key
        last_error = ""
        for attempt in range(self.max_retries):
            wait = self.min_interval - (time.monotonic() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.monotonic()
            try:
                response = self.session.get(f"{BASE_URL}{path}", params=params, timeout=90)
            except requests.RequestException as error:
                time.sleep(2**attempt)
                last_error = repr(error)
                continue
            self.requests_made += 1
            self.remaining = response.headers.get("x-ratelimit-remaining", self.remaining)
            if response.status_code == 200:
                return response.json()
            last_error = f"HTTP {response.status_code}: {response.text[:300]}"
            if response.status_code == 429:
                # OpenAlex returns 429 both for burst limits and for an exhausted daily budget.
                if self.remaining is not None and self.remaining.strip() in {"0", "-1"}:
                    raise BudgetExhausted(last_error)
                if "credits" in response.text.lower() or "budget" in response.text.lower():
                    raise BudgetExhausted(last_error)
                time.sleep(min(60, 2 ** (attempt + 1)))
                continue
            if response.status_code >= 500:
                time.sleep(2 ** (attempt + 1))
                continue
            safe_params = {key: value for key, value in params.items() if key != "api_key"}
            raise RuntimeError(f"OpenAlex request failed for {path} {safe_params}: {last_error}")
        if last_error.startswith("HTTP 429"):
            # Still rate limited after every retry: treat as an exhausted budget and wait for the next run.
            raise BudgetExhausted(last_error)
        raise RuntimeError(f"OpenAlex request failed after {self.max_retries} retries: {last_error}")

    def paginate(
        self, path: str, params: dict[str, Any], cursor: str = "*"
    ) -> Iterator[tuple[list[dict[str, Any]], str | None, int]]:
        """Yield (results, next_cursor, total_count) for each page using cursor paging."""
        while cursor:
            data = self.get(path, {**params, "per_page": 200, "cursor": cursor})
            cursor = data["meta"].get("next_cursor")
            yield data["results"], cursor, data["meta"]["count"]
            if not data["results"]:
                break
