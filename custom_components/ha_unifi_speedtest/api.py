import requests
import logging
import urllib3
from requests.exceptions import HTTPError

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_LOGGER = logging.getLogger(__name__)

class UniFiAPI:
    def __init__(self, url, username, password, site='default', verify_ssl=False):
        self.url = url
        self.username = username
        self.password = password
        self.site = site
        self.verify_ssl = verify_ssl
        self.session = requests.Session()

    def login(self):
        login_endpoint = f"{self.url}/api/auth/login"
        credentials = {"username": self.username, "password": self.password}
        response = self.session.post(login_endpoint, json=credentials, verify=self.verify_ssl)
        response.raise_for_status()

    def _make_request(self, method, endpoint, **kwargs):
        try:
            response = method(endpoint, verify=self.verify_ssl, **kwargs)
            response.raise_for_status()
            return response
        except HTTPError as e:
            if e.response.status_code == 401:
                _LOGGER.info("Token expired, attempting to refresh...")
                self.login()
                response = method(endpoint, verify=self.verify_ssl, **kwargs)
                response.raise_for_status()
                return response
            raise

    def start_speed_test(self):
        endpoint = f"{self.url}/proxy/network/api/s/{self.site}/cmd/devmgr"
        payload = {"cmd": "speedtest"}
        self._make_request(self.session.post, endpoint, json=payload)

    def get_speed_test_status(self):
        endpoint = f"{self.url}/proxy/network/v2/api/site/{self.site}/speedtest"
        _LOGGER.debug(f"Requesting speed test data from: {endpoint}")
        
        try:
            response = self._make_request(self.session.get, endpoint)
            data = response.json()
            
            if 'data' in data and len(data['data']) > 0:
                latest_test = data['data'][-1]
                result = {
                    'download': latest_test.get('download_mbps', None),
                    'upload': latest_test.get('upload_mbps', None),
                    'ping': latest_test.get('latency_ms', None),
                    'jitter': None
                }
                _LOGGER.debug(f"Extracted speed test result: {result}")
                return result
            
            _LOGGER.warning("No speed test data found")
            return {'download': None, 'upload': None, 'ping': None, 'jitter': None}
            
        except Exception as e:
            _LOGGER.error(f"Error fetching speed test data: {e}")
            return {'download': None, 'upload': None, 'ping': None, 'jitter': None}
