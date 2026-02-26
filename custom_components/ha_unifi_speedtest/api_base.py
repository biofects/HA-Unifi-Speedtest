"""Base API class for UniFi Controllers."""
import logging
from datetime import datetime
from typing import Any, Dict, Optional

import requests
import urllib3
from requests import Response
from requests.exceptions import HTTPError, RequestException, Timeout
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_LOGGER = logging.getLogger(__name__)


class UniFiAPIBase:
    """Base class for UniFi API clients with common functionality."""

    def __init__(
        self,
        url: str,
        site: str = "default",
        verify_ssl: bool = False,
        controller_type: str = "udm",
        enable_multi_wan: bool = True,
    ) -> None:
        self.url = url.rstrip("/")
        self.site: str = site or "default"
        self.verify_ssl = verify_ssl
        self.controller_type = controller_type
        self.enable_multi_wan = enable_multi_wan

        # Create session with retry strategy and proper SSL handling
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "HomeAssistant-UniFi-Speedtest/3.x",
            "Accept": "application/json, text/plain, */*",
        })
        
        # Configure adapter with retry logic for both HTTP and HTTPS
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "POST", "PUT", "DELETE", "OPTIONS", "TRACE"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        # Set verify globally on session for consistency
        self.session.verify = verify_ssl

        # Cached site UUID for integration endpoints
        self._site_id: Optional[str] = None

    def _request(
        self,
        method,
        path: str,
        *,
        json: Any = None,
        params: Dict[str, Any] | None = None,
        timeout=(10, 30)
    ) -> Response:
        """Make an HTTP request with error handling.
        
        Note: This is a synchronous method designed to be called via
        hass.async_add_executor_job() to avoid blocking the event loop.
        """
        url = f"{self.url}{path}"
        try:
            # This blocking call is intentional - called via executor job
            # verify is already set on session, no need to pass explicitly
            resp = method(url, json=json, params=params, timeout=timeout)
            resp.raise_for_status()
            return resp
        except HTTPError as e:
            actual_url = getattr(getattr(e, 'response', None), 'url', None)
            _LOGGER.error(
                f"HTTP error for {url}: {e} - actual url: {actual_url} - "
                f"Response: {getattr(getattr(e, 'response', None), 'text', '')[:300]}"
            )
            raise
        except (RequestException, Timeout) as e:
            _LOGGER.error(f"Request error for {url}: {e}")
            raise

    @staticmethod
    def _safe_float(value):
        """Safely convert value to float."""
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _format_timestamp(timestamp_ms):
        """Convert millisecond timestamp to ISO format."""
        if timestamp_ms is None:
            return None
        try:
            ts = int(timestamp_ms) / 1000
            dt = datetime.fromtimestamp(ts)
            return dt.isoformat()
        except Exception:
            return None

    def get_controller_info(self) -> dict:
        """Get controller information."""
        return {
            "type": self.controller_type,
            "site": self.site,
            "url": self.url,
        }

    def get_health_status(self) -> dict:
        """Get API health status."""
        return {
            "can_connect": True,
            "consecutive_403s": 0,
            "in_cooldown": False,
            "cooldown_until": None,
        }
