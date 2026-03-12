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
        
        login_path = "/api/login"
        login_data = {
            "username": self.username,
            "password": self.password,
            "remember": True
        }

        try:
            # verify is already set on session
            resp = self.session.post(
                f"{self.url}{login_path}",
                json=login_data,
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

        # 1) Standard devmgr speedtest command (most common)
        attempts.append((f"/api/s/{site_internal}/cmd/devmgr", {"cmd": "speedtest"}))

        # 2) Direct speedtest endpoint if supported (newer versions)
        attempts.append((f"/api/s/{site_internal}/cmd/devmgr/speedtest", {}))
        
        # 3) Alternative sdn endpoint (some versions)
        attempts.append((f"/api/s/{site_internal}/cmd/sdn", {"cmd": "speedtest"}))
        
        # 4) V2 endpoint (very new versions)
        attempts.append((f"/v2/api/site/{site_internal}/speedtest", {}))

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
        
        # Try multiple endpoints - more options for better compatibility
        endpoints_to_try = [
            (f"/api/s/{site_internal}/stat/health", "health"),
            (f"/api/s/{site_internal}/stat/speedtest", "speedtest"),
            (f"/api/s/{site_internal}/stat/speedtest-results", "speedtest"),
            (f"/v2/api/site/{site_internal}/speedtest", "speedtest_v2"),
        ]
        
        wan_data = None
        
        for path, endpoint_type in endpoints_to_try:
            try:
                _LOGGER.debug(f"Trying endpoint: {path}")
                resp = self._request(self.session.get, path)
                data = resp.json() or {}
                
                if endpoint_type == "health":
                    # Parse health endpoint - find www subsystem
                    subsystems = data.get("data", [])
                    www_data = None
                    for subsystem in subsystems:
                        if subsystem.get("subsystem") == "www":
                            www_data = subsystem
                            break
                    
                    if www_data:
                        # Extract speedtest data from www subsystem
                        timestamp_s = www_data.get("speedtest_lastrun")
                        timestamp_ms = timestamp_s * 1000 if timestamp_s else None
                        
                        wan_data = {
                            "interface_name": "wan",
                            "wan_networkgroup": "WAN",
                            "download": self._safe_float(www_data.get("xput_down")),
                            "upload": self._safe_float(www_data.get("xput_up")),
                            "ping": self._safe_float(www_data.get("speedtest_ping")),
                            "timestamp": self._format_timestamp(timestamp_ms),
                            "status": www_data.get("speedtest_status", "unknown").lower(),
                            "id": str(timestamp_s) if timestamp_s else None,
                        }
                        _LOGGER.debug(f"Successfully parsed health endpoint: {wan_data}")
                        break
                    else:
                        _LOGGER.debug("No www subsystem found in health data")
                        continue
                        
                elif endpoint_type == "speedtest_v2":  # v2 endpoint
                    tests = data.get("data", [])
                    if tests:
                        # Get most recent test
                        latest = tests[0] if isinstance(tests, list) else tests
                        
                        wan_data = {
                            "interface_name": "wan",
                            "wan_networkgroup": "WAN",
                            "download": self._safe_float(latest.get("download_mbps") or latest.get("xput_down")),
                            "upload": self._safe_float(latest.get("upload_mbps") or latest.get("xput_up")),
                            "ping": self._safe_float(latest.get("latency_ms") or latest.get("speedtest_ping")),
                            "timestamp": self._format_timestamp(latest.get("time")),
                            "status": latest.get("status_text", "completed").lower(),
                            "id": latest.get("id"),
                        }
                        _LOGGER.debug(f"Successfully parsed speedtest v2 endpoint: {wan_data}")
                        break
                    else:
                        _LOGGER.debug("No speedtest data found in v2 endpoint")
                        continue
                        
                else:  # speedtest endpoint
                    tests = data.get("data", [])
                    if tests:
                        # Get most recent test
                        latest = max(tests, key=lambda x: x.get("_id", ""))
                        
                        wan_data = {
                            "interface_name": "wan",
                            "wan_networkgroup": "WAN",
                            "download": self._safe_float(latest.get("xput_download") or latest.get("xput_down")),
                            "upload": self._safe_float(latest.get("xput_upload") or latest.get("xput_up")),
                            "ping": self._safe_float(latest.get("latency") or latest.get("speedtest_ping")),
                            "timestamp": self._format_timestamp(latest.get("timestamp")),
                            "status": "completed",
                            "id": latest.get("_id"),
                        }
                        _LOGGER.debug(f"Successfully parsed speedtest endpoint: {wan_data}")
                        break
                    else:
                        _LOGGER.debug("No speedtest data found in speedtest endpoint")
                        continue
                        
            except Exception as e:
                _LOGGER.debug(f"Failed to get data from {path}: {e}")
                continue
        
        if not wan_data:
            _LOGGER.warning("No speedtest data found from any endpoint")
            return {
                "wan_interfaces": [],
                "total_interfaces": 0,
                "primary_wan": None,
                "multi_wan_enabled": False,
            }
        
        return {
            "wan_interfaces": [wan_data],
            "total_interfaces": 1,
            "primary_wan": "wan_WAN",
            "multi_wan_enabled": False,
            "platform_type": "controller",
            "detection_method": "legacy_health_api",
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
            # Use stat/health endpoint which is more widely supported
            resp = self._request(self.session.get, f"/api/s/{site_internal}/stat/health")
            data = resp.json()
            # Verify we got valid data back
            if "data" in data:
                _LOGGER.info("Connection test successful")
                return True
            else:
                _LOGGER.warning("Connection test returned unexpected data format")
                return False
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
