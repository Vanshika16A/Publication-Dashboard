"""Small OpenAlex API client: retries, optional API key, cursor paging.

Optional environment variables (or a `.env` file at the repository root):
    OPENALEX_API_KEY   free key from https://openalex.org/settings/api (raises the daily limit)
    OPENALEX_MAILTO    your e-mail, sent as a courtesy so OpenAlex can contact heavy users
"""

from __future__ import annotations

import os
import time
from typing import Any, Iterator

import requests

from .config import ROOT

BASE_URL = "https://api.openalex.org"


class BudgetExhausted(RuntimeError):
    """OpenAlex says the daily request budget is used up. Progress is saved; rerun later."""


def _setting(name: str) -> str | None:
    value = os.environ.get(name)
    if value:
        return value.strip()
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith(f"{name}="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def short_id(value: str | None) -> str:
    """'https://openalex.org/W123' -> 'W123'."""
    return value.rsplit("/", 1)[-1] if value else ""


class OpenAlexClient:
    def __init__(self, min_interval: float = 0.1, max_retries: int = 6) -> None:
        self.session = requests.Session()
        self.mailto = _setting("OPENALEX_MAILTO")
        agent = "DPCN-Group16-collector/1.0"
        self.session.headers["User-Agent"] = f"{agent} (mailto:{self.mailto})" if self.mailto else agent
        self.api_key = _setting("OPENALEX_API_KEY")
        self.min_interval = min_interval
        self.max_retries = max_retries
        self.requests_made = 0
        self.remaining: str | None = None
        self._last_call = 0.0

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = dict(params or {})
        if self.mailto:
            params["mailto"] = self.mailto
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
                last_error = repr(error)
                time.sleep(2**attempt)
                continue
            self.requests_made += 1
            self.remaining = response.headers.get("x-ratelimit-remaining", self.remaining)
            if response.status_code == 200:
                return response.json()
            last_error = f"HTTP {response.status_code}: {response.text[:300]}"
            if response.status_code == 429:
                text = response.text.lower()
                if (self.remaining or "").strip() in {"0", "-1"} or "budget" in text or "credits" in text:
                    raise BudgetExhausted(last_error)
                time.sleep(min(60, 2 ** (attempt + 1)))
                continue
            if response.status_code >= 500:
                time.sleep(2 ** (attempt + 1))
                continue
            safe = {k: v for k, v in params.items() if k != "api_key"}
            raise RuntimeError(f"OpenAlex request failed for {path} {safe}: {last_error}")
        if last_error.startswith("HTTP 429"):
            raise BudgetExhausted(last_error)
        raise RuntimeError(f"OpenAlex request failed after {self.max_retries} tries: {last_error}")

    def paginate(self, path: str, params: dict[str, Any], cursor: str = "*") -> Iterator[tuple[list[dict], str | None, int]]:
        """Yield (results, next_cursor, total_count) per page (200 results per page)."""
        while cursor:
            data = self.get(path, {**params, "per_page": 200, "cursor": cursor})
            cursor = data["meta"].get("next_cursor")
            yield data["results"], cursor, data["meta"]["count"]
            if not data["results"]:
                break
