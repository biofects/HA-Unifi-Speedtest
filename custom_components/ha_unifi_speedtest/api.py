import requests
import logging
import urllib3
from requests.exceptions import HTTPError

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_LOGGER = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

class UniFiAPI:
    def __init__(self, url, username, password, site='default', verify_ssl=False, controller_type='udm'):
        _LOGGER.info(f"Initializing UniFiAPI: url={url}, site={site}, verify_ssl={verify_ssl}, controller_type={controller_type}")
        self.url = url
        self.username = username
        self.password = password
        self.site = site
        self.verify_ssl = verify_ssl
        self.controller_type = controller_type
        self.session = requests.Session()

    def login(self):
        """Login to UniFi Controller based on specified type"""
        if self.controller_type == 'udm':
            self._login_udm()
        else:
            self._login_controller()

    def _login_udm(self):
        """Login to UDM Pro/Cloud Key"""
        login_endpoint = f"{self.url}/api/auth/login"
        credentials = {"username": self.username, "password": self.password}
        _LOGGER.info(f"Logging in to UDM Pro at {login_endpoint}")
        response = self.session.post(login_endpoint, json=credentials, verify=self.verify_ssl)
        _LOGGER.info(f"UDM login response status: {response.status_code}")
        response.raise_for_status()
        _LOGGER.info("UDM login successful.")

    def _login_controller(self):
        """Login to traditional UniFi Controller"""
        login_endpoint = f"{self.url}/api/login"
        credentials = {"username": self.username, "password": self.password}
        _LOGGER.info(f"Logging in to UniFi Controller at {login_endpoint}")
        response = self.session.post(login_endpoint, json=credentials, verify=self.verify_ssl)
        _LOGGER.info(f"Controller login response status: {response.status_code}")
        response.raise_for_status()
        _LOGGER.info("Controller login successful.")

    def _make_request(self, method, endpoint, **kwargs):
        _LOGGER.info(f"Making request to endpoint: {endpoint}")
        try:
            response = method(endpoint, verify=self.verify_ssl, **kwargs)
            _LOGGER.info(f"Response status: {response.status_code}")
            response.raise_for_status()
            return response
        except HTTPError as e:
            if e.response.status_code == 401:
                _LOGGER.info("Token expired, attempting to refresh...")
                self.login()
                response = method(endpoint, verify=self.verify_ssl, **kwargs)
                _LOGGER.info(f"Response status after refresh: {response.status_code}")
                response.raise_for_status()
                return response
            _LOGGER.error(f"HTTPError encountered: {e}")
            raise

    def start_speed_test(self):
        """Start speed test on the appropriate controller type"""
        if self.controller_type == 'udm':
            _LOGGER.warning("UDM Pro speed test not supported via API - please use UniFi Network web interface")
            raise Exception("UDM Pro speed test not supported via API")
        else:
            self._start_speed_test_controller()

    def _start_speed_test_controller(self):
        """Start speed test on traditional controller"""
        endpoint = f"{self.url}/api/s/{self.site}/cmd/devmgr"
        payload = {"cmd": "speedtest"}
        _LOGGER.info(f"Starting Controller speed test at endpoint: {endpoint}")
        self._make_request(self.session.post, endpoint, json=payload)

    def get_speed_test_status(self):
        """Get speed test status from the appropriate controller type"""
        if self.controller_type == 'udm':
            return self._get_speed_test_status_udm()
        else:
            return self._get_speed_test_status_controller()

    def _get_speed_test_status_udm(self):
        """Get speed test status from UDM Pro"""
        endpoint = f"{self.url}/proxy/network/v2/api/site/{self.site}/speedtest"
        _LOGGER.info(f"Requesting UDM speed test data from: {endpoint}")
        try:
            response = self._make_request(self.session.get, endpoint)
            data = response.json()
            _LOGGER.info(f"UDM Speed test data received: {data}")
            if 'data' in data and len(data['data']) > 0:
                latest_test = data['data'][-1]
                result = {
                    'download': latest_test.get('download_mbps', None),
                    'upload': latest_test.get('upload_mbps', None),
                    'ping': latest_test.get('latency_ms', None),
                    'jitter': None  # UDM doesn't provide jitter in this endpoint
                }
                _LOGGER.info(f"Extracted UDM speed test result: {result}")
                return result
            _LOGGER.warning("No UDM speed test data found")
            return {'download': None, 'upload': None, 'ping': None, 'jitter': None}
        except Exception as e:
            _LOGGER.error(f"Error fetching UDM speed test data: {e}")
            return {'download': None, 'upload': None, 'ping': None, 'jitter': None}

    def _get_speed_test_status_controller(self):
        """Get speed test status from traditional UniFi Controller"""
        endpoint = f"{self.url}/api/s/{self.site}/stat/health"
        _LOGGER.info(f"Requesting Controller speed test data from: {endpoint}")
        try:
            response = self._make_request(self.session.get, endpoint)
            data = response.json()
            _LOGGER.info(f"Controller Speed test data received: {data}")
            
            if 'data' in data and len(data['data']) > 0:
                # Look for the health data that contains speed test info
                health_data = data['data'][0]  # Usually the first item contains the speed test data
                
                # Extract values and convert to match UDM format
                download_mbps = health_data.get('xput_down')
                upload_mbps = health_data.get('xput_up') 
                ping_ms = health_data.get('speedtest_ping')
                
                result = {
                    'download': float(download_mbps) if download_mbps is not None else None,
                    'upload': float(upload_mbps) if upload_mbps is not None else None,
                    'ping': float(ping_ms) if ping_ms is not None else None,
                    'jitter': None  # Controller health endpoint doesn't provide jitter
                }
                _LOGGER.info(f"Extracted Controller speed test result: {result}")
                return result
            
            _LOGGER.warning("No Controller speed test data found")
            return {'download': None, 'upload': None, 'ping': None, 'jitter': None}
        except Exception as e:
            _LOGGER.error(f"Error fetching Controller speed test data: {e}")
            return {'download': None, 'upload': None, 'ping': None, 'jitter': None}

    def get_controller_info(self):
        """Get information about the controller type and version"""
        return {
            'type': self.controller_type,
            'site': self.site,
            'url': self.url
        }