import requests
import logging
import urllib3
from requests.exceptions import HTTPError, RequestException, Timeout
from datetime import datetime, timedelta
import time
import random
import asyncio
from threading import Lock

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_LOGGER = logging.getLogger(__name__)

class UniFiAPI:
    def __init__(self, url, username, password, site='default', verify_ssl=False, controller_type='udm'):
        _LOGGER.info(f"Initializing UniFiAPI: url={url}, site={site}, verify_ssl={verify_ssl}, controller_type={controller_type}")
        self.url = url.rstrip('/')  # Remove trailing slash if present
        self.username = username
        self.password = password
        self.site = site
        self.verify_ssl = verify_ssl
        self.controller_type = controller_type
        self.session = requests.Session()
        # Set reasonable timeouts
        self.session.timeout = (10, 30)  # (connect timeout, read timeout)
        self._last_login = None
        self._login_valid_duration = 1800  # Reduced to 30 minutes for more frequent reauth
        self._last_403_time = None
        self._rate_limit_backoff = 0
        self._consecutive_403s = 0
        self._max_consecutive_403s = 3
        self._global_rate_limit = datetime.now()
        self._min_request_interval = 5  # Minimum 5 seconds between requests
        self._login_lock = Lock()  # Thread safety for login
        self._last_request_time = None
        self._failed_login_count = 0
        self._max_failed_logins = 3
        self._login_cooldown_until = None
        
        # Enhanced session configuration
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (compatible; HomeAssistant UniFi Speedtest)',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache'
        })

    def _is_login_valid(self):
        """Check if current login is still valid"""
        if not self._last_login:
            return False
        return (datetime.now() - self._last_login).total_seconds() < self._login_valid_duration

    def _is_in_login_cooldown(self):
        """Check if we're in a login cooldown period"""
        if self._login_cooldown_until is None:
            return False
        return datetime.now() < self._login_cooldown_until

    def _enforce_rate_limit(self):
        """Enforce minimum time between requests"""
        if self._last_request_time:
            time_since_last = (datetime.now() - self._last_request_time).total_seconds()
            if time_since_last < self._min_request_interval:
                sleep_time = self._min_request_interval - time_since_last
                _LOGGER.debug(f"Rate limiting: sleeping for {sleep_time:.1f} seconds")
                time.sleep(sleep_time)
        self._last_request_time = datetime.now()

    def login(self):
        """Login to UniFi Controller based on specified type with enhanced error handling"""
        with self._login_lock:  # Ensure thread safety
            # Check if we're in cooldown
            if self._is_in_login_cooldown():
                remaining_cooldown = (self._login_cooldown_until - datetime.now()).total_seconds()
                _LOGGER.warning(f"Login cooldown active, {remaining_cooldown:.0f} seconds remaining")
                raise Exception(f"Login temporarily disabled due to repeated failures. Try again in {remaining_cooldown:.0f} seconds.")
            
            try:
                # Clear any existing session cookies to start fresh
                self.session.cookies.clear()
                
                if self.controller_type == 'udm':
                    self._login_udm()
                else:
                    self._login_controller()
                
                self._last_login = datetime.now()
                self._failed_login_count = 0  # Reset on successful login
                self._consecutive_403s = 0  # Reset 403 counter on successful login
                self._login_cooldown_until = None  # Clear cooldown
                _LOGGER.info("Login successful")
                
            except Exception as e:
                self._last_login = None
                self._failed_login_count += 1
                
                if "403" in str(e) or "Forbidden" in str(e):
                    self._consecutive_403s += 1
                    _LOGGER.warning(f"Login failed with 403 error (attempt {self._failed_login_count}/{self._max_failed_logins})")
                
                # Implement login cooldown after repeated failures
                if self._failed_login_count >= self._max_failed_logins:
                    cooldown_minutes = min(30, 5 * self._failed_login_count)  # Progressive cooldown, max 30 min
                    self._login_cooldown_until = datetime.now() + timedelta(minutes=cooldown_minutes)
                    _LOGGER.error(f"Too many login failures, implementing {cooldown_minutes} minute cooldown")
                
                _LOGGER.error(f"Login failed: {e}")
                raise

    def _login_udm(self):
        """Login to UDM Pro/Cloud Key with enhanced error handling"""
        login_endpoint = f"{self.url}/api/auth/login"
        credentials = {"username": self.username, "password": self.password}
        
        # Add additional headers that might be expected
        headers = {
            'Content-Type': 'application/json',
            'Origin': self.url,
            'Referer': f"{self.url}/",
        }
        
        _LOGGER.info(f"Logging in to UDM Pro at {login_endpoint}")
        
        try:
            self._enforce_rate_limit()
            response = self.session.post(
                login_endpoint, 
                json=credentials, 
                verify=self.verify_ssl,
                timeout=(15, 45),  # Longer timeout for login
                headers=headers
            )
            _LOGGER.info(f"UDM login response status: {response.status_code}")
            
            if response.status_code == 403:
                _LOGGER.warning("UDM login returned 403 - possible rate limiting or account lockout")
                
            response.raise_for_status()
            
            # Verify we got expected response structure
            if response.headers.get('content-type', '').startswith('application/json'):
                try:
                    login_data = response.json()
                    _LOGGER.debug("Login response contains JSON data")
                except:
                    pass
            
            _LOGGER.info("UDM login successful.")
            
        except Exception as e:
            _LOGGER.error(f"UDM login failed: {e}")
            if hasattr(e, 'response') and e.response is not None:
                _LOGGER.error(f"Response content: {e.response.text[:500]}")
            raise

    def _login_controller(self):
        """Login to traditional UniFi Controller with enhanced error handling"""
        login_endpoint = f"{self.url}/api/login"
        credentials = {"username": self.username, "password": self.password}
        
        _LOGGER.info(f"Logging in to UniFi Controller at {login_endpoint}")
        
        try:
            self._enforce_rate_limit()
            response = self.session.post(
                login_endpoint, 
                json=credentials, 
                verify=self.verify_ssl,
                timeout=(15, 45)
            )
            _LOGGER.info(f"Controller login response status: {response.status_code}")
            response.raise_for_status()
            _LOGGER.info("Controller login successful.")
            
        except Exception as e:
            _LOGGER.error(f"Controller login failed: {e}")
            raise

    def _ensure_authenticated(self):
        """Ensure we have a valid authentication session"""
        if not self._is_login_valid():
            _LOGGER.info("Authentication session expired or invalid, re-authenticating...")
            self.login()

    def _handle_rate_limit(self):
        """Handle rate limiting with enhanced exponential backoff"""
        now = datetime.now()
        
        # Increase consecutive 403 counter
        self._consecutive_403s += 1
        
        if self._last_403_time:
            time_since_403 = (now - self._last_403_time).total_seconds()
            if time_since_403 < 600:  # Within 10 minutes of last 403
                self._rate_limit_backoff = min(self._rate_limit_backoff * 1.5, 300)  # Cap at 5 minutes
            else:
                self._rate_limit_backoff = 30  # Reset to 30 seconds
        else:
            self._rate_limit_backoff = 30
        
        # Progressive backoff based on consecutive 403s
        if self._consecutive_403s > self._max_consecutive_403s:
            # Implement longer cooldown for persistent 403s
            extended_backoff = min(600, 60 * self._consecutive_403s)  # Up to 10 minutes
            self._rate_limit_backoff = max(self._rate_limit_backoff, extended_backoff)
            _LOGGER.warning(f"Too many consecutive 403s ({self._consecutive_403s}), extended backoff: {extended_backoff}s")
        
        # Add jitter to avoid thundering herd
        jitter = random.uniform(0.8, 1.2)
        backoff_time = self._rate_limit_backoff * jitter
        
        _LOGGER.warning(f"Rate limit detected (consecutive: {self._consecutive_403s}), backing off for {backoff_time:.1f} seconds")
        time.sleep(backoff_time)
        self._last_403_time = now

    def _make_request(self, method, endpoint, max_retries=2, **kwargs):
        """Make HTTP request with automatic login retry and enhanced rate limit handling"""
        _LOGGER.debug(f"Making request to endpoint: {endpoint}")
        
        # Ensure we're authenticated before making the request
        self._ensure_authenticated()
        
        # Enforce global rate limiting
        self._enforce_rate_limit()
        
        for attempt in range(max_retries + 1):
            try:
                # Set timeout if not already specified
                if 'timeout' not in kwargs:
                    kwargs['timeout'] = (15, 45)  # Increased timeouts
                
                response = method(endpoint, verify=self.verify_ssl, **kwargs)
                _LOGGER.debug(f"Response status: {response.status_code}")
                
                # Check for successful response
                if response.status_code == 200:
                    # Reset consecutive 403 counter on successful request
                    if self._consecutive_403s > 0:
                        _LOGGER.info("Successful request, resetting 403 counter")
                        self._consecutive_403s = 0
                        self._rate_limit_backoff = 0
                    return response
                
                response.raise_for_status()
                return response
                
            except HTTPError as e:
                if e.response.status_code == 403:
                    _LOGGER.warning(f"403 Forbidden error on attempt {attempt + 1}/{max_retries + 1}")
                    
                    if attempt < max_retries:
                        self._handle_rate_limit()
                        
                        # Try re-authenticating after rate limit backoff
                        try:
                            _LOGGER.info("Attempting re-authentication after 403 error")
                            self.login()
                        except Exception as login_error:
                            _LOGGER.error(f"Re-authentication after 403 failed: {login_error}")
                            if attempt == max_retries - 1:  # Last attempt
                                raise
                        
                        continue
                    else:
                        _LOGGER.error(f"Rate limit exceeded after {max_retries + 1} attempts")
                        raise
                        
                elif e.response.status_code == 401 and attempt < max_retries:
                    _LOGGER.info(f"Authentication failed on attempt {attempt + 1}, re-authenticating...")
                    try:
                        self.login()
                        time.sleep(2)  # Wait before retry
                        continue
                    except Exception as login_error:
                        _LOGGER.error(f"Re-authentication failed: {login_error}")
                        raise
                else:
                    _LOGGER.error(f"HTTPError on attempt {attempt + 1}: {e}")
                    raise
                    
            except (RequestException, Timeout) as e:
                if attempt < max_retries:
                    wait_time = (attempt + 1) * 5  # Progressive wait
                    _LOGGER.warning(f"Request failed on attempt {attempt + 1}, retrying in {wait_time}s: {e}")
                    time.sleep(wait_time)
                    continue
                else:
                    _LOGGER.error(f"Request failed after {max_retries + 1} attempts: {e}")
                    raise

    def start_speed_test(self):
        """Start speed test on the appropriate controller type with enhanced error handling"""
        _LOGGER.info(f"Starting speed test on {self.controller_type} controller at {datetime.now()}")
        
        # Check if we're hitting too many 403s
        if self._consecutive_403s > self._max_consecutive_403s:
            raise Exception(f"Too many consecutive 403 errors ({self._consecutive_403s}), avoiding further requests")
        
        try:
            if self.controller_type == 'udm':
                self._start_speed_test_udm()
            else:
                self._start_speed_test_controller()
            _LOGGER.info("Speed test initiation completed successfully")
        except Exception as e:
            _LOGGER.error(f"Speed test initiation failed: {e}")
            raise

    def _get_csrf_token(self):
        """Get CSRF token from the UDM Pro interface with error handling"""
        try:
            # Try to get CSRF token from a lightweight endpoint
            status_endpoint = f"{self.url}/proxy/network/api/s/{self.site}/stat/health"
            
            # Make a simple GET request to get headers/cookies
            response = self.session.get(status_endpoint, verify=self.verify_ssl, timeout=(10, 20))
            
            # Check various header names for CSRF token
            csrf_headers = ['X-Csrf-Token', 'x-csrf-token', 'X-CSRF-TOKEN', 'csrf-token']
            for header in csrf_headers:
                csrf_token = response.headers.get(header)
                if csrf_token:
                    _LOGGER.debug(f"CSRF token obtained from {header} header")
                    return csrf_token
                    
            # Alternative: try to extract from cookies
            for cookie in self.session.cookies:
                if 'csrf' in cookie.name.lower():
                    _LOGGER.debug("CSRF token obtained from cookies")
                    return cookie.value
                    
            _LOGGER.debug("No CSRF token found")
            return None
            
        except Exception as e:
            _LOGGER.warning(f"Failed to get CSRF token: {e}")
            return None

    def _start_speed_test_udm(self):
        """Start speed test on UDM Pro with enhanced error handling"""
        endpoint = f"{self.url}/proxy/network/api/s/{self.site}/cmd/devmgr/speedtest"
        _LOGGER.info(f"Starting UDM Pro speed test at endpoint: {endpoint}")
        
        # Prepare headers to match browser request
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json, text/plain, */*',
            'Origin': self.url,
            'Referer': f"{self.url}/",
            'X-Requested-With': 'XMLHttpRequest'
        }
        
        # Get CSRF token - but don't fail if we can't get it
        try:
            csrf_token = self._get_csrf_token()
            if csrf_token:
                headers['X-Csrf-Token'] = csrf_token
                _LOGGER.debug("Added CSRF token to request headers")
        except Exception as e:
            _LOGGER.debug(f"Could not obtain CSRF token, continuing without: {e}")
        
        # Try different payloads in order of preference
        payloads_to_try = [
            {},  # Empty JSON object
            {"cmd": "speedtest"},  # Traditional command format
        ]
        
        last_exception = None
        
        for i, payload in enumerate(payloads_to_try):
            try:
                _LOGGER.debug(f"Attempting UDM Pro speed test with payload {i+1}: {payload}")
                response = self._make_request(
                    self.session.post, 
                    endpoint, 
                    json=payload,
                    headers=headers,
                    max_retries=1  # Reduced retries for speed test to avoid prolonged failures
                )
                
                try:
                    data = response.json()
                    _LOGGER.info(f"UDM Pro speed test response: {data}")
                except ValueError:
                    _LOGGER.info("UDM Pro speed test initiated (no JSON response)")
                
                _LOGGER.info("UDM Pro speed test started successfully")
                return  # Success, exit the function
                
            except Exception as e:
                last_exception = e
                _LOGGER.warning(f"UDM Pro speed test attempt {i+1} failed: {e}")
                continue  # Try next payload
        
        # If we got here, all attempts failed
        _LOGGER.error(f"All UDM Pro speed test attempts failed. Last error: {last_exception}")
        raise last_exception

    def _start_speed_test_controller(self):
        """Start speed test on traditional controller with enhanced error handling"""
        endpoint = f"{self.url}/api/s/{self.site}/cmd/devmgr"
        
        # Try different payloads
        payloads_to_try = [
            {"cmd": "speedtest"},  # Standard command
        ]
        
        _LOGGER.info(f"Starting Controller speed test at endpoint: {endpoint}")
        
        last_exception = None
        
        for i, payload in enumerate(payloads_to_try):
            try:
                _LOGGER.debug(f"Attempting Controller speed test with payload {i+1}: {payload}")
                response = self._make_request(
                    self.session.post, 
                    endpoint, 
                    json=payload,
                    max_retries=1
                )
                try:
                    data = response.json()
                    _LOGGER.info(f"Controller speed test response: {data}")
                except ValueError:
                    _LOGGER.info("Controller speed test initiated (no JSON response)")
                
                _LOGGER.info("Controller speed test started successfully")
                return  # Success, exit the function
                
            except Exception as e:
                last_exception = e
                _LOGGER.warning(f"Controller speed test attempt {i+1} failed: {e}")
                continue  # Try next payload
        
        # If we got here, all attempts failed
        _LOGGER.error(f"All Controller speed test attempts failed. Last error: {last_exception}")
        raise last_exception

    def get_speed_test_status(self):
        """Get speed test status from the appropriate controller type"""
        _LOGGER.debug(f"Getting speed test status from {self.controller_type} controller")
        
        # Check if we should skip this request due to rate limiting
        if self._consecutive_403s > self._max_consecutive_403s:
            _LOGGER.warning("Skipping status request due to too many 403 errors")
            return {'download': None, 'upload': None, 'ping': None}
        
        try:
            if self.controller_type == 'udm':
                return self._get_speed_test_status_udm()
            else:
                return self._get_speed_test_status_controller()
        except Exception as e:
            _LOGGER.error(f"Failed to get speed test status: {e}")
            # Return empty result instead of crashing
            return {'download': None, 'upload': None, 'ping': None}

    def _get_speed_test_status_udm(self):
        """Get speed test status from UDM Pro with enhanced error handling"""
        # Try multiple endpoints for UDM data
        endpoints_to_try = [
            f"{self.url}/proxy/network/api/s/{self.site}/stat/health",
            f"{self.url}/proxy/network/v2/api/site/{self.site}/speedtest",
            f"{self.url}/proxy/network/api/s/{self.site}/stat/speedtest"
        ]
        
        for endpoint in endpoints_to_try:
            try:
                _LOGGER.debug(f"Requesting UDM speed test data from: {endpoint}")
                response = self._make_request(self.session.get, endpoint, max_retries=1)
                data = response.json()
                
                # Handle different response formats
                if 'data' in data and len(data['data']) > 0:
                    if 'speedtest' in endpoint or 'v2/api' in endpoint:
                        # New format from v2 API or speedtest endpoint
                        latest_test = data['data'][-1]
                        result = {
                            'download': latest_test.get('download_mbps', latest_test.get('xput_down')),
                            'upload': latest_test.get('upload_mbps', latest_test.get('xput_up')),
                            'ping': latest_test.get('latency_ms', latest_test.get('speedtest_ping'))
                        }
                    else:
                        # Health endpoint format - look for www subsystem
                        www_data = None
                        for subsystem in data['data']:
                            if subsystem.get('subsystem') == 'www':
                                www_data = subsystem
                                break
                        
                        if www_data:
                            result = {
                                'download': www_data.get('xput_down'),
                                'upload': www_data.get('xput_up'),
                                'ping': www_data.get('speedtest_ping')
                            }
                        else:
                            continue  # Try next endpoint
                    
                    # Convert to float if not None
                    for key in result:
                        if result[key] is not None:
                            try:
                                result[key] = float(result[key])
                            except (ValueError, TypeError):
                                result[key] = None
                    
                    _LOGGER.debug(f"Extracted UDM speed test result from {endpoint}: {result}")
                    return result
                    
            except Exception as e:
                _LOGGER.debug(f"Failed to get data from {endpoint}: {e}")
                continue
        
        _LOGGER.debug("No UDM speed test data found from any endpoint")
        return {'download': None, 'upload': None, 'ping': None}

    def _get_speed_test_status_controller(self):
        """Get speed test status from traditional UniFi Controller with enhanced error handling"""
        # Try multiple endpoints for controller data
        endpoints_to_try = [
            f"{self.url}/api/s/{self.site}/stat/health",
            f"{self.url}/api/s/{self.site}/stat/speedtest"
        ]
        
        for endpoint in endpoints_to_try:
            try:
                _LOGGER.debug(f"Requesting Controller speed test data from: {endpoint}")
                response = self._make_request(self.session.get, endpoint, max_retries=1)
                data = response.json()
                
                if 'data' in data and len(data['data']) > 0:
                    if 'speedtest' in endpoint:
                        # Direct speedtest endpoint
                        latest_test = data['data'][-1]
                        result = {
                            'download': latest_test.get('xput_down'),
                            'upload': latest_test.get('xput_up'),
                            'ping': latest_test.get('speedtest_ping')
                        }
                    else:
                        # Health endpoint - look for the 'www' subsystem
                        www_data = None
                        for subsystem in data['data']:
                            if subsystem.get('subsystem') == 'www':
                                www_data = subsystem
                                break
                        
                        if www_data:
                            result = {
                                'download': www_data.get('xput_down'),
                                'upload': www_data.get('xput_up'),
                                'ping': www_data.get('speedtest_ping'),
                                'status': www_data.get('speedtest_status')
                            }
                        else:
                            continue  # Try next endpoint
                    
                    # Convert to float if not None
                    for key in ['download', 'upload', 'ping']:
                        if result.get(key) is not None:
                            try:
                                result[key] = float(result[key])
                            except (ValueError, TypeError):
                                result[key] = None
                    
                    _LOGGER.debug(f"Extracted Controller speed test result from {endpoint}: {result}")
                    return result
                    
            except Exception as e:
                _LOGGER.debug(f"Failed to get data from {endpoint}: {e}")
                continue
        
        _LOGGER.debug("No Controller speed test data found from any endpoint")
        return {'download': None, 'upload': None, 'ping': None, 'status': None}

    def get_controller_info(self):
        """Get information about the controller type and version"""
        return {
            'type': self.controller_type,
            'site': self.site,
            'url': self.url,
            'consecutive_403s': self._consecutive_403s,
            'rate_limit_backoff': self._rate_limit_backoff,
            'last_login': self._last_login.isoformat() if self._last_login else None
        }

    def test_connection(self):
        """Test the connection to the controller with enhanced error handling"""
        try:
            self.login()
            # Try to get some basic data to verify the connection works
            if self.controller_type == 'udm':
                test_endpoint = f"{self.url}/proxy/network/api/s/{self.site}/stat/health"
            else:
                test_endpoint = f"{self.url}/api/s/{self.site}/stat/health"
            
            response = self._make_request(self.session.get, test_endpoint, max_retries=1)
            data = response.json()
            
            if 'data' in data:
                _LOGGER.info("Connection test successful")
                return True
            else:
                _LOGGER.warning("Connection test returned unexpected data format")
                return False
                
        except Exception as e:
            _LOGGER.error(f"Connection test failed: {e}")
            return False

    def get_health_status(self):
        """Get basic health info to check if we can connect without triggering speed tests"""
        return {
            'can_connect': not self._is_in_login_cooldown(),
            'consecutive_403s': self._consecutive_403s,
            'in_cooldown': self._is_in_login_cooldown(),
            'cooldown_until': self._login_cooldown_until.isoformat() if self._login_cooldown_until else None,
            'last_login': self._last_login.isoformat() if self._last_login else None,
            'failed_login_count': self._failed_login_count
        }