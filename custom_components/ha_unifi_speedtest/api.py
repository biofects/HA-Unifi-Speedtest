import requests
import logging
import json
import urllib3

# Suppress the InsecureRequestWarning
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

    def start_speed_test(self):
        endpoint = f"{self.url}/proxy/network/api/s/{self.site}/cmd/devmgr"
        payload = {"cmd": "speedtest"}
        response = self.session.post(endpoint, json=payload, verify=self.verify_ssl)
        response.raise_for_status()

    def get_speed_test_status(self):
        endpoint = f"{self.url}/proxy/network/v2/api/site/{self.site}/speedtest"
        _LOGGER.debug(f"Requesting speed test data from: {endpoint}")
        
        try:
            response = self.session.get(endpoint, verify=self.verify_ssl)
            response.raise_for_status()
            data = response.json()
            
            # Check if we have speed test data
            if 'data' in data and len(data['data']) > 0:
                # Take the most recent speed test result (last item in the list)
                latest_test = data['data'][-1]
                
                result = {
                    'download': latest_test.get('download_mbps', None),
                    'upload': latest_test.get('upload_mbps', None),
                    'ping': latest_test.get('latency_ms', None),
                    'jitter': None  # Not present in this data structure
                }
                
                _LOGGER.debug(f"Extracted speed test result: {result}")
                return result
            
            # Fallback if no data is found
            _LOGGER.warning("No speed test data found")
            return {
                'download': None,
                'upload': None,
                'ping': None,
                'jitter': None
            }
        
        except requests.exceptions.RequestException as e:
            _LOGGER.error(f"Network error fetching speed test data: {e}")
            return {
                'download': None,
                'upload': None,
                'ping': None,
                'jitter': None
            }
        except ValueError as e:
            _LOGGER.error(f"JSON parsing error: {e}")
            return {
                'download': None,
                'upload': None,
                'ping': None,
                'jitter': None
            }
        except Exception as e:
            _LOGGER.error(f"Unexpected error fetching speed test data: {e}")
            return {
                'download': None,
                'upload': None,
                'ping': None,
                'jitter': None
            }
