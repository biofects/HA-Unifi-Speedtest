"""API client for Self-hosted Software Controllers (Username/Password Authentication)."""
import logging
from typing import Any, Dict, List, Optional, Tuple

try:
    from .api_base import UniFiAPIBase
except ImportError:
    from api_base import UniFiAPIBase

_LOGGER = logging.getLogger(__name__)


class UniFiSoftwareAPI(UniFiAPIBase):
    """UniFi API client for self-hosted Network Application using session authentication.
    
    Supports: Self-hosted UniFi Network Application installations.
    Uses username/password with cookie-based session authentication.
    """

    def __init__(
        self,
        url: str,
        username: str,
        password: str,
        site: str = "default",
        verify_ssl: bool = False,
        enable_multi_wan: bool = True,
    ) -> None:
        super().__init__(url, site, verify_ssl, "controller", enable_multi_wan)
        self.username = username
        self.password = password
        
        # Session management
        self._logged_in = False
        self._csrf_token = None
        
        _LOGGER.info("Initialized UniFi Software Controller API with username/password authentication")

    def login(self) -> None:
        """Login to create session. Required before any API calls."""
        if self._logged_in:
            _LOGGER.debug("Already logged in, reusing session")
            return

        _LOGGER.info("Logging in to software controller with username/password")
        
        login_path = "/api/auth/login"
        login_data = {
            "username": self.username,
            "password": self.password,
            "remember": True
        }

        try:
            resp = self.session.post(
                f"{self.url}{login_path}",
                json=login_data,
                verify=self.verify_ssl,
                timeout=(10, 30)
            )
            resp.raise_for_status()
            
            # Extract CSRF token if present
            self._csrf_token = resp.headers.get('X-CSRF-Token') or resp.headers.get('x-csrf-token')
            if self._csrf_token:
                self.session.headers['X-CSRF-Token'] = self._csrf_token
                _LOGGER.debug("CSRF token obtained and added to session headers")
            
            self._logged_in = True
            _LOGGER.info("Login successful, session established")
            
        except Exception as e:
            _LOGGER.error(f"Login failed: {e}")
            self._logged_in = False
            raise

    def _resolve_site_ids(self) -> Tuple[str, str]:
        """Resolve site information. For software controllers, site == site ID."""
        # Ensure we're logged in
        self.login()
        
        # Software controllers typically use the site name directly
        # No UUID resolution needed - the site name IS the identifier
        _LOGGER.debug(f"Using site: {self.site}")
        return self.site, self.site

    def start_speed_test(self, interface_name: Optional[str] = None) -> dict:
        """Trigger a UniFi speed test.
        
        Args:
            interface_name: Optional interface name (may not be supported on all controllers)
        """
        self.login()
        
        site_internal, _ = self._resolve_site_ids()
        _LOGGER.info(f"Triggering speed test on site '{site_internal}'")

        # Try multiple endpoints
        attempts: List[Tuple[str, Dict[str, Any]]] = []

        # 1) Standard devmgr speedtest command
        attempts.append((f"/api/s/{site_internal}/cmd/devmgr", {"cmd": "speedtest"}))

        # 2) Direct speedtest endpoint if supported
        attempts.append((f"/api/s/{site_internal}/cmd/devmgr/speedtest", {}))

        last_error: Optional[Exception] = None
        for path, payload in attempts:
            try:
                resp = self._request(self.session.post, path, json=payload, timeout=(10, 45))
                try:
                    return resp.json()
                except Exception:
                    return {"result": "ok", "path": path}
            except Exception as e:
                last_error = e
                status = getattr(getattr(e, 'response', None), 'status_code', None)
                if status not in (400, 401, 403, 404, 405):
                    raise
                _LOGGER.debug(f"Speedtest endpoint {path} failed (status: {status}), trying next")
                continue

        if last_error:
            raise last_error
        return {"result": "failed"}

    def get_wan_interfaces(self) -> List[Dict[str, Any]]:
        """List configured WANs. Software controllers typically have single WAN.
        
        Note: Multi-WAN detection is limited on software controllers.
        """
        self.login()
        
        # Software controllers don't have the same integration endpoint
        # Return a default WAN interface
        _LOGGER.debug("Software controller: returning default WAN interface")
        return [{
            "name": "WAN",
            "type": "wan",
            "network_group": "WAN",
            "network_name": "WAN",
        }]

    def get_speed_test_status(self) -> dict:
        """Return latest speedtest status.
        
        Software controllers typically support single WAN only.
        """
        self.login()
        
        site_internal, _ = self._resolve_site_ids()
        path = f"/api/s/{site_internal}/stat/speedtest"
        
        try:
            resp = self._request(self.session.get, path)
            data = resp.json() or {}
        except Exception as e:
            _LOGGER.error(f"Failed to get speedtest status: {e}")
            return {
                "wan_interfaces": [],
                "total_interfaces": 0,
                "primary_wan": None,
                "multi_wan_enabled": False,
            }
        
        tests = data.get("data", [])
        if not tests:
            return {
                "wan_interfaces": [],
                "total_interfaces": 0,
                "primary_wan": None,
                "multi_wan_enabled": False,
            }
        
        # Get most recent test
        latest = max(tests, key=lambda x: x.get("_id", ""))
        
        # Format as single WAN result
        wan_data = {
            "interface_name": "wan",
            "wan_networkgroup": "WAN",
            "download": self._safe_float(latest.get("xput_download")),
            "upload": self._safe_float(latest.get("xput_upload")),
            "ping": self._safe_float(latest.get("latency")),
            "timestamp": self._format_timestamp(latest.get("timestamp")),
            "status": "completed",
            "id": latest.get("_id"),
        }
        
        return {
            "wan_interfaces": [wan_data],
            "total_interfaces": 1,
            "primary_wan": "wan_WAN",
            "multi_wan_enabled": False,
            "platform_type": "controller",
            "detection_method": "legacy_speedtest_api",
        }

    def get_wan_status_map(self) -> Dict[str, Dict[str, Any]]:
        """Return WAN interface status map.
        
        Limited functionality on software controllers.
        """
        self.login()
        
        # Software controllers have limited WAN status visibility
        _LOGGER.debug("Software controller: WAN status map not fully supported")
        return {}

    def get_controller_info(self) -> dict:
        """Get controller information."""
        self.login()
        
        try:
            site_internal, _ = self._resolve_site_ids()
            path = f"/api/s/{site_internal}/stat/sysinfo"
            resp = self._request(self.session.get, path)
            data = resp.json() or {}
            
            if data.get("data"):
                info = data["data"][0] if isinstance(data["data"], list) else data["data"]
                return {
                    'type': self.controller_type,
                    'version': info.get('version', 'unknown'),
                    'name': info.get('name', 'UniFi Controller'),
                    'site': self.site,
                    'url': self.url,
                }
        except Exception as e:
            _LOGGER.debug(f"Could not get controller info: {e}")
        
        return {
            'type': self.controller_type,
            'version': 'unknown',
            'name': 'UniFi Controller',
            'site': self.site,
            'url': self.url,
        }

    def test_connection(self) -> bool:
        """Test API connection."""
        try:
            self.login()
            site_internal, _ = self._resolve_site_ids()
            _ = self._request(self.session.get, f"/api/s/{site_internal}/stat/speedtest")
            return True
        except Exception as e:
            _LOGGER.error(f"Connection test failed: {e}")
            return False

    def get_health_status(self) -> dict:
        """Get API health status with session information."""
        return {
            "can_connect": True,
            "consecutive_403s": 0,
            "in_cooldown": False,
            "cooldown_until": None,
            "logged_in": self._logged_in,
        }
