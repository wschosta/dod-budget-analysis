"""An empty discovery result must never be cached.

Finding zero files is far more likely to be a WAF challenge page, a selector
that no longer matches, or a network block than a fiscal year that genuinely
published nothing. Caching it turns every later retry into a silent no-op.

That is not hypothetical: army_2024.json and airforce_2026.json were found on
disk containing `"files": []`, written when those hosts returned HTTP 403 and
a TLS refusal. With them present the downloader could not recover even from a
network able to reach the sites.

This file is separate from test_source_resilience.py deliberately — that
module has an autouse fixture mocking _save_cache, which would make these
tests assert against the mock instead of the function.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import downloader.sources as src  # noqa: E402


def test_empty_result_writes_no_cache_file(tmp_path):
    with patch.object(src, "DISCOVERY_CACHE_DIR", tmp_path):
        src._save_cache("army_2024", [])
    assert list(tmp_path.glob("*.json")) == [], (
        "an empty discovery was cached; retries would be suppressed"
    )


def test_non_empty_result_is_cached(tmp_path):
    with patch.object(src, "DISCOVERY_CACHE_DIR", tmp_path):
        src._save_cache("army_2024", [{"filename": "x.pdf"}])
    written = list(tmp_path.glob("*.json"))
    assert [p.name for p in written] == ["army_2024.json"]
    assert json.loads(written[0].read_text())["files"] == [{"filename": "x.pdf"}]


def test_cached_result_round_trips(tmp_path):
    files = [{"filename": "APN_BA1-4_Book.pdf", "url": "https://x/y.pdf"}]
    with patch.object(src, "DISCOVERY_CACHE_DIR", tmp_path):
        src._save_cache("navy_2026", files)
        assert src._load_cache("navy_2026") == files
