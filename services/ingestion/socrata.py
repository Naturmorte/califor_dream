"""Minimal Socrata Open Data API client. Stdlib only, no API key required
for these datasets (confirmed via live requests, 2026-09-01)."""

import json
import urllib.parse
import urllib.request
from typing import Iterator, Optional

PAGE_SIZE = 1000
TIMEOUT_SECONDS = 30


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
        with urllib.request.urlopen(url, timeout=TIMEOUT_SECONDS) as resp:
            page = json.loads(resp.read().decode("utf-8"))
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
    with urllib.request.urlopen(url, timeout=TIMEOUT_SECONDS) as resp:
        page = json.loads(resp.read().decode("utf-8"))
    return int(page[0]["count"]) if page else 0
