"""API client for UDM/UniFi OS Hardware Controllers (API Key Authentication)."""
import logging
from typing import Any, Dict, List, Optional, Tuple

try:
    from .api_base import UniFiAPIBase
except ImportError:
    from api_base import UniFiAPIBase

_LOGGER = logging.getLogger(__name__)


class UniFiHardwareAPI(UniFiAPIBase):
    """UniFi API client for UDM/UniFi OS using API Key authentication.
    
    Supports: UDM Pro, UDM SE, Cloud Key Gen2+, and other UniFi OS devices.
    Uses X-API-KEY header for authentication.
    """

    def __init__(
        self,
        url: str,
        api_key: str,
        site: str = "default",
        verify_ssl: bool = False,
        enable_multi_wan: bool = True,
    ) -> None:
        super().__init__(url, site, verify_ssl, "udm", enable_multi_wan)
        self.api_key = api_key
        
        # Add API key to session headers
        self.session.headers["X-API-KEY"] = self.api_key
        
        _LOGGER.info("Initialized UniFi Hardware API with API key authentication")

    def _resolve_site_ids(self) -> Tuple[str, str]:
        """Resolve and cache site UUID based on internal reference.
        Returns (internal_reference, site_id_uuid)
        """
        if self._site_id is not None:
            return self.site, self._site_id

        path = "/proxy/network/integration/v1/sites"
        resp = self._request(self.session.get, path)
        data = resp.json() or {}
        
        for entry in data.get("data", []):
            if entry.get("internalReference") == self.site:
                self._site_id = entry.get("id")
                break
                
        # Fallback to first site if not matched
        if self._site_id is None and data.get("data"):
            first = data["data"][0]
            self.site = first.get("internalReference", self.site)
            self._site_id = first.get("id")
            
        if not self._site_id:
            raise RuntimeError("Unable to resolve UniFi site. Check API key and URL.")
            
        _LOGGER.debug(f"Resolved site: internal={self.site}, id={self._site_id}")
        return self.site, self._site_id

    def start_speed_test(self, interface_name: Optional[str] = None) -> dict:
        """Trigger a UniFi speed test.
        Tries multiple official endpoints to handle firmware differences.
        
        Args:
            interface_name: Optional interface name for specific WAN testing
        """
        site_internal, _ = self._resolve_site_ids()
        interface_msg = f" on interface {interface_name}" if interface_name else ""
        _LOGGER.info(f"Triggering speed test{interface_msg} on site '{site_internal}'")

        # Try multiple endpoints in order of preference
        attempts: List[Tuple[str, Dict[str, Any]]] = []

        # 1) Newer firmwares: explicit speedtest endpoint
        payload = {"interface_name": interface_name} if interface_name else {}
        attempts.append((f"/proxy/network/api/s/{site_internal}/cmd/devmgr/speedtest", payload))

        # 2) Legacy form: POST to cmd/devmgr with {"cmd":"speedtest"}
        legacy_payload: Dict[str, Any] = {"cmd": "speedtest"}
        if interface_name:
            legacy_payload["interface_name"] = interface_name
        attempts.append((f"/proxy/network/api/s/{site_internal}/cmd/devmgr", legacy_payload))

        # 3) v2 speedtest endpoint
        attempts.append((
            f"/proxy/network/v2/api/site/{site_internal}/speedtest",
            {} if not interface_name else {"interface_name": interface_name}
        ))
        
        # 4) Cloud Gateway / alternative endpoint (no /api/ in path)
        attempts.append((
            f"/proxy/network/s/{site_internal}/cmd/devmgr",
            {"cmd": "speedtest"} if not interface_name else {"cmd": "speedtest", "interface_name": interface_name}
        ))
        
        # 5) Direct v1 API endpoint (some devices)
        attempts.append((
            f"/api/s/{site_internal}/cmd/devmgr",
            {"cmd": "speedtest"} if not interface_name else {"cmd": "speedtest", "interface_name": interface_name}
        ))

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
        """List configured WANs using official integration endpoint."""
        site_internal, site_id = self._resolve_site_ids()
        
        # Try multiple endpoints for WAN discovery
        endpoints = [
            f"/proxy/network/integration/v1/sites/{site_id}/wans",
            f"/proxy/network/api/s/{site_internal}/rest/wanconf",
            f"/api/s/{site_internal}/rest/wanconf",
        ]
        
        data = None
        for path in endpoints:
            try:
                resp = self._request(self.session.get, path)
                data = resp.json() or {}
                if data.get("data"):
                    _LOGGER.debug(f"Using WAN interfaces endpoint: {path}")
                    break
            except Exception as e:
                _LOGGER.debug(f"WAN interfaces endpoint {path} failed: {e}")
                continue
        
        if not data or not data.get("data"):
            _LOGGER.warning("Could not discover WAN interfaces from any endpoint")
            return []
        
        wans = []
        for idx, wan in enumerate(data.get("data", []), start=1):
            group = f"WAN{'' if idx == 1 else idx}"
            name = group
            network_name = wan.get("name") or name
            wans.append({
                "name": name,
                "type": "wan",
                "network_group": group,
                "network_name": network_name,
            })
            
        _LOGGER.debug(f"Discovered {len(wans)} WANs: {[w['network_name'] for w in wans]}")
        return wans

    def get_speed_test_status(self) -> dict:
        """Return latest speedtest per WAN using official speedtest endpoint."""
        site_internal, _ = self._resolve_site_ids()
        
        # Try multiple endpoints for compatibility
        endpoints = [
            f"/proxy/network/v2/api/site/{site_internal}/speedtest",
            f"/proxy/network/api/s/{site_internal}/stat/speedtest",
            f"/api/s/{site_internal}/stat/speedtest-results",
            f"/api/s/{site_internal}/stat/speedtest",
        ]
        
        body = None
        last_error = None
        for path in endpoints:
            try:
                resp = self._request(self.session.get, path)
                body = resp.json() or {}
                if body.get("data") is not None:  # Found valid endpoint
                    _LOGGER.debug(f"Using speedtest status endpoint: {path}")
                    break
            except Exception as e:
                last_error = e
                _LOGGER.debug(f"Speedtest status endpoint {path} failed, trying next")
                continue
        
        if body is None:
            if last_error:
                _LOGGER.warning(f"All speedtest status endpoints failed, last error: {last_error}")
            return {
                "wan_interfaces": [],
                "total_interfaces": 0,
                "primary_wan": None,
                "multi_wan_enabled": True,
            }
            
        entries: List[dict] = body.get("data", [])
        
        if not entries:
            return {
                "wan_interfaces": [],
                "total_interfaces": 0,
                "primary_wan": None,
                "multi_wan_enabled": True,
            }

        # Keep last record per (interface_name, wan_networkgroup)
        latest: Dict[Tuple[str, str], dict] = {}
        entries_sorted = sorted(entries, key=lambda e: e.get("time", 0))
        
        for e in entries_sorted:
            iface = e.get("interface_name") or e.get("interface") or e.get("ifname") or "unknown"
            group = e.get("wan_networkgroup") or e.get("wan_group") or "WAN"
            key = (iface, group)
            latest[key] = {
                "interface_name": iface,
                "wan_networkgroup": group,
                "download": self._safe_float(e.get("download_mbps", e.get("xput_down"))),
                "upload": self._safe_float(e.get("upload_mbps", e.get("xput_up"))),
                "ping": self._safe_float(e.get("latency_ms", e.get("speedtest_ping"))),
                "timestamp": self._format_timestamp(e.get("time")),
                "status": e.get("status_text", e.get("status", "completed")),
                "id": e.get("id"),
            }

        wan_list = list(latest.values())

        # Determine primary WAN
        primary_key = None
        for k, v in latest.items():
            if str(v.get("wan_networkgroup")).upper() == "WAN":
                primary_key = f"{v['interface_name']}_{v['wan_networkgroup']}"
                break
                
        if not primary_key and wan_list:
            wan_list_sorted = sorted(
                wan_list,
                key=lambda x: (x.get("download") or 0.0, x.get("timestamp") or ""),
                reverse=True,
            )
            v = wan_list_sorted[0]
            primary_key = f"{v['interface_name']}_{v['wan_networkgroup']}"

        return {
            "wan_interfaces": wan_list,
            "total_interfaces": len(wan_list),
            "primary_wan": primary_key,
            "multi_wan_enabled": True,
            "platform_type": "udm",
            "detection_method": "official_speedtest_api",
        }

    def get_wan_status_map(self) -> Dict[str, Dict[str, Any]]:
        """Return WAN interface status map."""
        site_internal, _ = self._resolve_site_ids()
        
        # Try multiple endpoints for device status
        endpoints = [
            f"/proxy/network/api/s/{site_internal}/stat/device",
            f"/api/s/{site_internal}/stat/device",
        ]
        
        body = None
        for path in endpoints:
            try:
                resp = self._request(self.session.get, path)
                body = resp.json()
                if body:
                    _LOGGER.debug(f"Using device status endpoint: {path}")
                    break
            except Exception as e:
                _LOGGER.debug(f"Device status endpoint {path} failed: {e}")
                continue
        
        if not body:
            _LOGGER.debug("WAN status map fetch failed - no valid endpoint found")
            return {}

        devices: List[Dict[str, Any]] = []
        if isinstance(body, dict):
            devices = body.get("data", []) if isinstance(body.get("data"), list) else []
        elif isinstance(body, list):
            devices = body

        _LOGGER.info(f"Found {len(devices)} devices")

        # Find gateway device
        gw = None
        for d in devices:
            t = (d.get("type") or d.get("device_type") or "").lower()
            model = (d.get("model") or d.get("shortname") or "").lower()
            _LOGGER.debug(f"Device: type={t}, model={model}")
            if t in ("udm", "udmpro", "udm-se", "ugw", "usg", "uxg") or any(x in model for x in ["udm", "ugw", "usg"]):
                gw = d
                _LOGGER.info(f"Found gateway device: type={t}, model={model}")
                break
                
        if not gw:
            _LOGGER.debug("No gateway device found in device list")
            return {}

        status_map: Dict[str, Dict[str, Any]] = {}
        
        # Parse interface table
        if_table = gw.get("if_table") or gw.get("ifTable")
        if not if_table:
            _LOGGER.debug("Gateway device has no if_table or ifTable")
            return {}
            
        _LOGGER.info(f"Gateway has {len(if_table) if isinstance(if_table, list) else 0} interfaces")
        
        if isinstance(if_table, list):
            for it in if_table:
                name = it.get("name") or it.get("ifname")
                if not name:
                    continue
                up = bool(it.get("up", it.get("link_state", it.get("active", False))))
                ip = it.get("ip") or it.get("ip_address") or None
                
                # Additional info to determine if WAN is truly active
                speed = it.get("speed") or 0
                full_duplex = it.get("full_duplex", False)
                rx_bytes = it.get("rx_bytes", 0)
                tx_bytes = it.get("tx_bytes", 0)
                
                # Consider WAN truly active if:
                # 1. Link is up
                # 2. Has valid IP (not 0.x.x.x)
                # 3. Has speed negotiated (speed > 0)
                # 4. Has some traffic (rx_bytes or tx_bytes > 0)
                is_active = (
                    up and 
                    ip and 
                    not str(ip).startswith('0.') and
                    speed > 0 and
                    (rx_bytes > 0 or tx_bytes > 0)
                )
                
                status_map[name] = {
                    "up": up, 
                    "ip": ip,
                    "speed": speed,
                    "full_duplex": full_duplex,
                    "rx_bytes": rx_bytes,
                    "tx_bytes": tx_bytes,
                    "is_active": is_active
                }
                _LOGGER.debug(f"Interface {name}: up={up}, ip={ip}, speed={speed}, rx={rx_bytes}, tx={tx_bytes}, is_active={is_active}")

        _LOGGER.info(f"WAN status map built with {len(status_map)} interfaces")
        return status_map

    def test_connection(self) -> bool:
        """Test API connection."""
        try:
            site_internal, _ = self._resolve_site_ids()
            _ = self._request(self.session.get, f"/proxy/network/v2/api/site/{site_internal}/speedtest")
            return True
        except Exception as e:
            _LOGGER.error(f"Connection test failed: {e}")
            return False
