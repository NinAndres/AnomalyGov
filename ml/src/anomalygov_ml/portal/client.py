"""Client of the Portal da Transparência API (AGENTS.md, section 5.1; decision 0014).

The key goes only in the `chave-api-dados` header, read from PORTAL_API_KEY, and never appears in logs or
messages. Requests are spaced to stay under the Portal limit (PORTAL_API_REQUESTS_PER_MINUTE, default 80,
below the daytime limit of 90 per minute), and 429, 5xx and network errors are retried with growing waits.
"""

import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterator
from typing import Any

BASE_URL = "https://api.portaldatransparencia.gov.br/api-de-dados"
DEFAULT_REQUESTS_PER_MINUTE = 80
MAX_RETRIES = 5
BACKOFF_SECONDS = 2.0  # doubles on each retry: 2, 4, 8, 16, 32
MAX_WAIT_SECONDS = 120.0
TIMEOUT_SECONDS = 30
log = logging.getLogger("anomalygov.portal")


class PortalError(Exception):
    """Failure of the Portal API whose message can be shown to the user."""


class PortalClient:
    def __init__(self, api_key: str, requests_per_minute: float = DEFAULT_REQUESTS_PER_MINUTE,
                 base_url: str = BASE_URL, opener: Callable[..., Any] = urllib.request.urlopen,
                 sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic):
        if not api_key:
            raise PortalError("A consulta ao Portal não está configurada no worker (PORTAL_API_KEY).")
        self._key = api_key
        self._interval = 60.0 / requests_per_minute
        self._base_url = base_url.rstrip("/")
        self._opener = opener
        self._sleep = sleep
        self._clock = clock
        self._last_request: float | None = None
        self.requests = 0

    @classmethod
    def from_env(cls) -> "PortalClient":
        return cls(os.environ.get("PORTAL_API_KEY", ""),
                   float(os.environ.get("PORTAL_API_REQUESTS_PER_MINUTE", DEFAULT_REQUESTS_PER_MINUTE)))

    def __repr__(self) -> str:
        return f"PortalClient(base_url={self._base_url!r})"

    def _throttle(self) -> None:
        if self._last_request is not None:
            wait = self._last_request + self._interval - self._clock()
            if wait > 0:
                self._sleep(wait)
        self._last_request = self._clock()

    def get(self, endpoint: str, params: dict[str, Any]) -> Any:
        """GET one endpoint (e.g. "/cartoes") and return the decoded JSON."""
        url = f"{self._base_url}{endpoint}?{urllib.parse.urlencode(params)}"
        for attempt in range(MAX_RETRIES + 1):
            self._throttle()
            self.requests += 1
            request = urllib.request.Request(url, headers={"chave-api-dados": self._key, "Accept": "application/json"})
            try:
                with self._opener(request, timeout=TIMEOUT_SECONDS) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as error:
                if error.code in (401, 403):
                    raise PortalError("A API do Portal recusou a chave de acesso do worker.") from None
                if error.code != 429 and error.code < 500:
                    raise PortalError(f"A API do Portal recusou a consulta (HTTP {error.code}).") from None
                reason = f"HTTP {error.code}"
                retry_after = error.headers.get("Retry-After") if error.headers else None
            except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
                reason = type(error).__name__
                retry_after = None
            if attempt == MAX_RETRIES:
                raise PortalError(f"A API do Portal não respondeu após {MAX_RETRIES + 1} tentativas ({reason}).")
            wait = BACKOFF_SECONDS * 2**attempt
            if retry_after is not None and retry_after.strip().isdigit():
                wait = max(wait, float(retry_after))
            wait = min(wait, MAX_WAIT_SECONDS)
            # Only the endpoint is logged: the key is in a header and the params carry no personal data.
            log.warning("Portal: %s em %s; nova tentativa em %.0fs", reason, endpoint, wait)
            self._sleep(wait)
        raise AssertionError("unreachable")

    def pages(self, endpoint: str, params: dict[str, Any]) -> Iterator[list[dict[str, Any]]]:
        """Yield the pages of a paginated endpoint until an empty or short page.

        The page size is not documented, so a page shorter than the largest seen so far is taken as the last.
        """
        largest = 0
        page = 1
        while True:
            items = self.get(endpoint, {**params, "pagina": page})
            if not isinstance(items, list):
                raise PortalError("A API do Portal devolveu uma resposta em formato inesperado.")
            if not items:
                return
            yield items
            if len(items) < largest:
                return
            largest = max(largest, len(items))
            page += 1
