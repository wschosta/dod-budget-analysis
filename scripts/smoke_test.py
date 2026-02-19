#!/usr/bin/env python3
"""
BEAR-005: Smoke test script for deployment verification.

Validates a running deployment by checking key endpoints.

Usage:
    python scripts/smoke_test.py                          # Default: localhost:8000
    python scripts/smoke_test.py --base-url http://staging:8000
    python scripts/smoke_test.py --timeout 10
"""
# DONE [Group: BEAR] BEAR-005: Add smoke test script for deployment verification (~2,000 tokens)

import argparse
import csv
import io
import json
import sys
import time
import urllib.request
import urllib.error


def check_endpoint(base_url: str, path: str, expected_status: int,
                   timeout: int = 5, validate_fn=None) -> tuple[bool, str]:
    """Check a single endpoint and return (success, message).

    Args:
        base_url: Base URL of the running service.
        path: Endpoint path (e.g., "/health").
        expected_status: Expected HTTP status code.
        timeout: Request timeout in seconds.
        validate_fn: Optional callable(response_body) -> bool for content checks.

    Returns:
        (passed, message) tuple.
    """
    url = f"{base_url.rstrip('/')}{path}"
    try:
        req = urllib.request.Request(url)
        response = urllib.request.urlopen(req, timeout=timeout)
        status = response.status
        body = response.read().decode("utf-8", errors="replace")

        if status != expected_status:
            return False, f"Expected {expected_status}, got {status}"

        if validate_fn and not validate_fn(body):
            return False, f"Response validation failed"

        return True, f"{status} OK"

    except urllib.error.HTTPError as e:
        if e.code == expected_status:
            return True, f"{e.code} (expected error code)"
        return False, f"HTTP {e.code}: {e.reason}"
    except urllib.error.URLError as e:
        return False, f"Connection failed: {e.reason}"
    except Exception as e:
        return False, f"Error: {e}"


def validate_json_non_empty(body: str) -> bool:
    """Validate that the body is valid JSON with non-empty content."""
    try:
        data = json.loads(body)
        if isinstance(data, list):
            return len(data) > 0
        if isinstance(data, dict):
            return len(data) > 0
        return True
    except (json.JSONDecodeError, ValueError):
        return False


def validate_csv_headers(body: str) -> bool:
    """Validate that the body looks like valid CSV with headers."""
    try:
        reader = csv.reader(io.StringIO(body))
        headers = next(reader, None)
        return headers is not None and len(headers) > 0
    except Exception:
        return False


def run_smoke_tests(base_url: str, timeout: int = 5) -> tuple[int, int, float]:
    """Run all smoke tests and return (passed, total, elapsed_seconds).

    Args:
        base_url: Base URL of the running service.
        timeout: Request timeout per check in seconds.

    Returns:
        (passed_count, total_count, elapsed_seconds) tuple.
    """
    start = time.monotonic()

    checks = [
        # (name, path, expected_status, validate_fn)
        ("Homepage (GET /)", "/", 200, None),
        ("Charts page (GET /charts)", "/charts", 200, None),
        ("Health check (GET /health)", "/health", 200, None),
        ("Health detailed (GET /health/detailed)", "/health/detailed", 200,
         validate_json_non_empty),
        ("Reference services (GET /api/v1/reference/services)", "/api/v1/reference/services",
         200, validate_json_non_empty),
        ("Search API (GET /api/v1/search?q=test)", "/api/v1/search?q=test",
         200, None),
        ("CSV download (GET /api/v1/download?format=csv&limit=5)",
         "/api/v1/download?format=csv&limit=5", 200, validate_csv_headers),
        ("Error handling (GET /api/v1/budget-lines?limit=-1)",
         "/api/v1/budget-lines?limit=-1", 422, None),
    ]

    passed = 0
    total = len(checks)

    print(f"\nSmoke Testing: {base_url}")
    print("=" * 60)

    for name, path, expected_status, validate_fn in checks:
        success, message = check_endpoint(base_url, path, expected_status,
                                          timeout=timeout, validate_fn=validate_fn)
        icon = "[PASS]" if success else "[FAIL]"
        print(f"  {icon} {name}: {message}")
        if success:
            passed += 1

    elapsed = time.monotonic() - start

    print("=" * 60)
    print(f"  Result: {passed}/{total} checks passed ({elapsed:.1f}s)")
    if passed == total:
        print("  Status: ALL PASSED")
    else:
        print(f"  Status: {total - passed} FAILED")
    print("=" * 60)

    return passed, total, elapsed


def main():
    parser = argparse.ArgumentParser(
        description="Smoke test a running DoD Budget API deployment")
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="Base URL of the running service (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=5,
        help="Timeout per request in seconds (default: 5)",
    )
    args = parser.parse_args()

    passed, total, elapsed = run_smoke_tests(args.base_url, timeout=args.timeout)
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
