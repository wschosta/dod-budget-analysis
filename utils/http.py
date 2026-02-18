"""HTTP and download utilities for DoD budget tools.

Provides reusable functions for:
- HTTP requests with retry logic
- Adaptive timeout management
- Caching mechanisms
- Connection pooling and session management
"""

import json
import time
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry as URLRetry


class RetryStrategy:
    """Defines retry behavior for HTTP requests."""

    def __init__(self, max_retries: int = 3, backoff_factor: float = 2.0,
                 status_forcelist: Optional[List[int]] = None):
        """Initialize retry strategy.

        Args:
            max_retries: Maximum number of retry attempts (default: 3)
            backoff_factor: Exponential backoff multiplier (default: 2.0)
                           delays: 2s, 4s, 8s, etc.
            status_forcelist: HTTP status codes to retry on
                            (default: [429, 500, 502, 503, 504])
        """
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.status_forcelist = status_forcelist or [429, 500, 502, 503, 504]

    def get_retry_object(self) -> URLRetry:
        """Get urllib3 Retry object configured with this strategy.

        Returns:
            urllib3.util.retry.Retry object
        """
        return URLRetry(
            total=self.max_retries,
            backoff_factor=self.backoff_factor,
            status_forcelist=self.status_forcelist,
            allowed_methods=["GET", "HEAD"]
        )


class SessionManager:
    """Manages HTTP sessions with connection pooling and retries."""

    def __init__(self, retry_strategy: Optional[RetryStrategy] = None,
                 pool_connections: int = 10, pool_maxsize: int = 20):
        """Initialize session manager.

        Args:
            retry_strategy: RetryStrategy to use (default: standard strategy)
            pool_connections: Number of connection pools to cache
            pool_maxsize: Maximum number of connections per pool
        """
        self.retry_strategy = retry_strategy or RetryStrategy()
        self.pool_connections = pool_connections
        self.pool_maxsize = pool_maxsize
        self._session: Optional[requests.Session] = None

    @property
    def session(self) -> requests.Session:
        """Get or create HTTP session with retries and pooling.

        Returns:
            requests.Session object
        """
        if self._session is None:
            self._session = requests.Session()

            # Configure retry strategy
            retry = self.retry_strategy.get_retry_object()

            # Mount for both http and https
            adapter = HTTPAdapter(
                max_retries=retry,
                pool_connections=self.pool_connections,
                pool_maxsize=self.pool_maxsize
            )
            self._session.mount("http://", adapter)
            self._session.mount("https://", adapter)

        return self._session

    def close(self) -> None:
        """Close the session and release resources."""
        if self._session:
            self._session.close()
            self._session = None

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


class TimeoutManager:
    """Manages adaptive timeouts based on response history."""

    def __init__(self, base_timeout: int = 30, min_timeout: int = 10,
                 max_timeout: int = 120, history_size: int = 20):
        """Initialize timeout manager.

        Args:
            base_timeout: Base timeout in seconds for new domains
            min_timeout: Minimum timeout in seconds
            max_timeout: Maximum timeout in seconds
            history_size: Number of response times to track per domain
        """
        self.base_timeout = base_timeout
        self.min_timeout = min_timeout
        self.max_timeout = max_timeout
        self.history_size = history_size
        self.response_times: Dict[str, List[float]] = {}

    def _get_domain(self, url: str) -> str:
        """Extract domain from URL.

        Args:
            url: Full URL

        Returns:
            Domain name
        """
        from urllib.parse import urlparse
        return urlparse(url).netloc

    def get_timeout(self, url: str) -> int:
        """Get adaptive timeout for URL based on response history.

        Uses 95th percentile of past response times + 50% buffer.

        Args:
            url: URL to request

        Returns:
            Timeout in seconds
        """
        domain = self._get_domain(url)

        if domain not in self.response_times or not self.response_times[domain]:
            return self.base_timeout

        times = self.response_times[domain]
        if len(times) < 3:
            return self.base_timeout

        # Calculate 95th percentile
        sorted_times = sorted(times)
        idx = int(len(sorted_times) * 0.95)
        percentile_95 = sorted_times[idx]

        # Apply 50% buffer
        adaptive = int(percentile_95 * 1.5)
        return min(max(adaptive, self.min_timeout), self.max_timeout)

    def record_time(self, url: str, elapsed_seconds: float) -> None:
        """Record response time for a URL.

        Args:
            url: URL requested
            elapsed_seconds: Time taken in seconds
        """
        domain = self._get_domain(url)

        if domain not in self.response_times:
            self.response_times[domain] = []

        self.response_times[domain].append(elapsed_seconds)

        # Keep only recent history
        if len(self.response_times[domain]) > self.history_size:
            self.response_times[domain].pop(0)


class CacheManager:
    """Manages file-based caching of HTTP responses.

    Stores responses as JSON files with timestamps for freshness checking.
    """

    def __init__(self, cache_dir: Path, ttl_hours: int = 24):
        """Initialize cache manager.

        Args:
            cache_dir: Directory to store cached files
            ttl_hours: Time-to-live for cached items in hours
        """
        self.cache_dir = Path(cache_dir)
        self.ttl_hours = ttl_hours
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_cache_path(self, key: str) -> Path:
        """Get cache file path for a key.

        Args:
            key: Cache key (should be URL-safe)

        Returns:
            Path to cache file
        """
        # Sanitize key to be filesystem-safe
        safe_key = "".join(c if c.isalnum() or c in '._-' else '_' for c in key)
        return self.cache_dir / f"{safe_key}.json"

    def get(self, key: str) -> Optional[Any]:
        """Get cached item if fresh.

        Args:
            key: Cache key

        Returns:
            Cached data if fresh, None if expired or missing
        """
        cache_file = self._get_cache_path(key)

        if not cache_file.exists():
            return None

        try:
            with open(cache_file, "r") as f:
                data = json.load(f)

            timestamp_str = data.get("timestamp")
            if not timestamp_str:
                return None

            timestamp = datetime.fromisoformat(timestamp_str)
            age = datetime.now() - timestamp

            if age > timedelta(hours=self.ttl_hours):
                return None

            return data.get("data")

        except (json.JSONDecodeError, OSError, ValueError):
            return None

    def put(self, key: str, data: Any) -> None:
        """Store item in cache.

        Args:
            key: Cache key
            data: Data to cache
        """
        cache_file = self._get_cache_path(key)

        cache_data = {
            "timestamp": datetime.now().isoformat(),
            "data": data
        }

        try:
            with open(cache_file, "w") as f:
                json.dump(cache_data, f, indent=2)
        except OSError as e:
            print(f"Warning: Failed to write cache file {cache_file}: {e}")

    def clear(self) -> None:
        """Clear all cached items."""
        for cache_file in self.cache_dir.glob("*.json"):
            try:
                cache_file.unlink()
            except OSError:
                pass

    def clear_expired(self) -> int:
        """Remove all expired cache items.

        Returns:
            Number of items removed
        """
        removed_count = 0

        for cache_file in self.cache_dir.glob("*.json"):
            try:
                with open(cache_file, "r") as f:
                    data = json.load(f)

                timestamp_str = data.get("timestamp")
                if not timestamp_str:
                    continue

                timestamp = datetime.fromisoformat(timestamp_str)
                age = datetime.now() - timestamp

                if age > timedelta(hours=self.ttl_hours):
                    cache_file.unlink()
                    removed_count += 1

            except (json.JSONDecodeError, OSError, ValueError):
                continue

        return removed_count


def download_file(url: str, dest_path: Path, session: Optional[requests.Session] = None,
                 timeout: int = 30, chunk_size: int = 8192) -> bool:
    """Download a file from URL to local path.

    Args:
        url: URL to download from
        dest_path: Local path to save to
        session: Optional requests.Session (default: new session)
        timeout: Request timeout in seconds
        chunk_size: Size of chunks to read (default: 8KB)

    Returns:
        True if successful, False otherwise
    """
    if session is None:
        session = requests.Session()

    try:
        resp = session.get(url, timeout=timeout, stream=True)
        resp.raise_for_status()

        dest_path.parent.mkdir(parents=True, exist_ok=True)

        with open(dest_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=chunk_size):
                if chunk:
                    f.write(chunk)

        return True

    except requests.RequestException as e:
        if dest_path.exists() and dest_path.stat().st_size == 0:
            dest_path.unlink()
        return False
