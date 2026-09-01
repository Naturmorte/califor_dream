"""Minimal Socrata Open Data API client. Stdlib only, no API key required
for these datasets (confirmed via live requests, 2026-09-01)."""

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Iterator, Optional

PAGE_SIZE = 1000
TIMEOUT_SECONDS = 30
MAX_RETRIES = 4
BACKOFF_BASE_SECONDS = 1.0


def _fetch_page(url: str) -> list:
    """GET with retry+backoff on transient errors (5xx, timeouts). Client
    errors (4xx - a bad query) are not retried, they'd just fail the same
    way again. Surfaces the real error after MAX_RETRIES, doesn't swallow it -
    a caller mid-pagination will have already committed prior rows, and
    idempotency (content_hash) makes a plain rerun safe (see docs/01)."""
    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            with urllib.request.urlopen(url, timeout=TIMEOUT_SECONDS) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code < 500:
                raise
            last_error = e
        except (urllib.error.URLError, TimeoutError) as e:
            last_error = e
        time.sleep(BACKOFF_BASE_SECONDS * (2 ** attempt))
    raise last_error


def fetch_records(
    domain: str,
    dataset_id: str,
    where: Optional[str] = None,
    order: Optional[str] = None,
    max_records: Optional[int] = None,
) -> Iterator[dict]:
    """Yields records from a Socrata dataset via $limit/$offset pagination.

    Stops when a page returns fewer than PAGE_SIZE rows, or when
    max_records is reached (if set).
    """
    offset = 0
    yielded = 0
    while True:
        params = {"$limit": PAGE_SIZE, "$offset": offset}
        if order:
            params["$order"] = order
        if where:
            params["$where"] = where
        url = f"https://{domain}/resource/{dataset_id}.json?" + urllib.parse.urlencode(params)
        page = _fetch_page(url)
        if not page:
            return
        for row in page:
            yield row
            yielded += 1
            if max_records is not None and yielded >= max_records:
                return
        if len(page) < PAGE_SIZE:
            return
        offset += PAGE_SIZE


def fetch_count(domain: str, dataset_id: str, where: Optional[str] = None) -> int:
    params = {"$select": "count(*)"}
    if where:
        params["$where"] = where
    url = f"https://{domain}/resource/{dataset_id}.json?" + urllib.parse.urlencode(params)
    page = _fetch_page(url)
    return int(page[0]["count"]) if page else 0
