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
    def __init__(self, url, username, password, site='default', verify_ssl=False, controller_type='udm', enable_multi_wan=True):
        _LOGGER.info(f"Initializing UniFiAPI: url={url}, site={site}, verify_ssl={verify_ssl}, controller_type={controller_type}, multi_wan={enable_multi_wan}")
        self.url = url.rstrip('/')  # Remove trailing slash if present
        self.username = username
        self.password = password
        self.site = site
        self.verify_ssl = verify_ssl
        self.controller_type = controller_type
        self.enable_multi_wan = enable_multi_wan  # New option for dual WAN support
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
            if self.enable_multi_wan:
                return {'wan_interfaces': [], 'total_interfaces': 0, 'primary_wan': None, 'multi_wan_enabled': True}
            else:
                return {'download': None, 'upload': None, 'ping': None}
        
        try:
            if self.enable_multi_wan:
                return self.get_speed_test_status_multi_wan()
            else:
                return self.get_speed_test_status_legacy()
        except Exception as e:
            _LOGGER.error(f"Failed to get speed test status: {e}")
            # Return empty result instead of crashing
            if self.enable_multi_wan:
                return {'wan_interfaces': [], 'total_interfaces': 0, 'primary_wan': None, 'multi_wan_enabled': True}
            else:
                return {'download': None, 'upload': None, 'ping': None}

    def get_speed_test_status_multi_wan(self):
        """Get speed test status with support for multiple WAN interfaces"""
        _LOGGER.debug("Getting speed test status with multi-WAN support")
        
        if self.controller_type == 'udm':
            return self._get_speed_test_status_udm_multi_wan()
        else:
            return self._get_speed_test_status_controller_multi_wan()

    def get_speed_test_status_legacy(self):
        """Legacy method for backward compatibility"""
        if self.controller_type == 'udm':
            return self._get_speed_test_status_udm()
        else:
            return self._get_speed_test_status_controller()

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

    def _get_speed_test_status_udm_multi_wan(self):
        """Get speed test status from UDM Pro/SE/Base with multi-WAN support"""
        # Try multiple endpoints with platform-specific optimizations
        endpoints_to_try = [
            f"{self.url}/proxy/network/v2/api/site/{self.site}/speedtest",
            f"{self.url}/proxy/network/api/s/{self.site}/stat/speedtest",
            f"{self.url}/proxy/network/api/s/{self.site}/stat/health"
        ]
        
        wan_interfaces = {}
        
        for endpoint in endpoints_to_try:
            try:
                _LOGGER.debug(f"Requesting UDM multi-WAN speed test data from: {endpoint}")
                response = self._make_request(self.session.get, endpoint, max_retries=1)
                data = response.json()
                
                if 'data' in data and len(data['data']) > 0:
                    _LOGGER.debug(f"Processing {len(data['data'])} entries from {endpoint}")
                    
                    if 'speedtest' in endpoint or 'v2/api' in endpoint:
                        # Direct speedtest endpoints - enhanced for all UDM variants
                        for entry in data['data']:
                            interface_name = entry.get('interface_name')
                            wan_group = entry.get('wan_networkgroup', 'WAN')
                            
                            # Enhanced interface detection for different UDM models
                            if not interface_name:
                                # Fallback interface detection
                                interface_name = entry.get('interface', 'unknown')
                            
                            if interface_name and interface_name != 'unknown':
                                wan_key = f"{interface_name}_{wan_group}"
                                
                                wan_interfaces[wan_key] = {
                                    'interface_name': interface_name,
                                    'wan_networkgroup': wan_group,
                                    'download': self._safe_float(entry.get('download_mbps')),
                                    'upload': self._safe_float(entry.get('upload_mbps')),
                                    'ping': self._safe_float(entry.get('latency_ms')),
                                    'timestamp': entry.get('time'),
                                    'id': entry.get('id'),
                                    'source_endpoint': endpoint
                                }
                    else:
                        # Health endpoint - enhanced for broader compatibility
                        for subsystem in data['data']:
                            subsystem_name = subsystem.get('subsystem', '')
                            
                            # Enhanced WAN detection for different platforms
                            is_wan_subsystem = (
                                'wan' in subsystem_name.lower() or 
                                subsystem_name == 'www' or 
                                'internet' in subsystem_name.lower() or
                                subsystem_name.startswith('WAN') or
                                'gateway' in subsystem_name.lower()
                            )
                            
                            if is_wan_subsystem:
                                # Enhanced interface extraction
                                interface_name = (
                                    subsystem.get('interface') or 
                                    subsystem.get('wan_interface') or
                                    subsystem.get('name') or
                                    subsystem_name
                                )
                                
                                wan_group = subsystem_name.upper() if subsystem_name != 'www' else 'WAN'
                                wan_key = f"{interface_name}_{wan_group}"
                                
                                wan_interfaces[wan_key] = {
                                    'interface_name': interface_name,
                                    'wan_networkgroup': wan_group,
                                    'download': self._safe_float(subsystem.get('xput_down')),
                                    'upload': self._safe_float(subsystem.get('xput_up')),
                                    'ping': self._safe_float(subsystem.get('speedtest_ping')),
                                    'timestamp': None,
                                    'id': None,
                                    'status': subsystem.get('status', 'unknown'),
                                    'source_endpoint': endpoint
                                }
                    
                    if wan_interfaces:
                        _LOGGER.info(f"Found {len(wan_interfaces)} WAN interface(s) on UDM platform: {list(wan_interfaces.keys())}")
                        break
                        
            except Exception as e:
                _LOGGER.debug(f"Failed to get multi-WAN data from {endpoint}: {e}")
                continue
        
        # Determine primary WAN more intelligently
        primary_wan = self._determine_primary_wan_udm(wan_interfaces) if wan_interfaces else None
        
        _LOGGER.info(f"UDM Multi-WAN detection complete: {len(wan_interfaces)} interfaces found, primary: {primary_wan}")
        _LOGGER.debug(f"WAN interfaces found: {list(wan_interfaces.keys())}")
        
        # Enhanced result with platform detection
        result = {
            'wan_interfaces': list(wan_interfaces.values()),
            'total_interfaces': len(wan_interfaces),
            'primary_wan': primary_wan,
            'multi_wan_enabled': True,
            'platform_type': 'udm',
            'detection_method': 'multi_endpoint_scan'
        }
        
        _LOGGER.debug(f"UDM Multi-WAN result: {result}")
        return result

    def _get_speed_test_status_controller_multi_wan(self):
        """Get speed test status from traditional UniFi Controller with multi-WAN support"""
        endpoints_to_try = [
            f"{self.url}/api/s/{self.site}/stat/speedtest",
            f"{self.url}/api/s/{self.site}/stat/health"
        ]
        
        wan_interfaces = {}
        
        for endpoint in endpoints_to_try:
            try:
                _LOGGER.debug(f"Requesting Controller multi-WAN speed test data from: {endpoint}")
                response = self._make_request(self.session.get, endpoint, max_retries=1)
                data = response.json()
                
                if 'data' in data and len(data['data']) > 0:
                    if 'speedtest' in endpoint:
                        # Direct speedtest endpoint - enhanced for software controller
                        for entry in data['data']:
                            interface_name = entry.get('interface_name', entry.get('interface', 'unknown'))
                            wan_group = entry.get('wan_networkgroup', entry.get('wan_group', 'WAN'))
                            
                            # Handle software controller variations
                            if interface_name and interface_name != 'unknown':
                                wan_key = f"{interface_name}_{wan_group}"
                                
                                wan_interfaces[wan_key] = {
                                    'interface_name': interface_name,
                                    'wan_networkgroup': wan_group,
                                    'download': self._safe_float(entry.get('xput_down', entry.get('download_mbps'))),
                                    'upload': self._safe_float(entry.get('xput_up', entry.get('upload_mbps'))),
                                    'ping': self._safe_float(entry.get('speedtest_ping', entry.get('latency_ms'))),
                                    'timestamp': entry.get('time'),
                                    'id': entry.get('id'),
                                    'source_endpoint': endpoint
                                }
                    else:
                        # Health endpoint - enhanced for software controller compatibility
                        for subsystem in data['data']:
                            subsystem_name = subsystem.get('subsystem', '')
                            
                            # Enhanced WAN detection for software controller
                            is_wan_subsystem = (
                                'wan' in subsystem_name.lower() or 
                                subsystem_name == 'www' or
                                'internet' in subsystem_name.lower() or
                                'gateway' in subsystem_name.lower() or
                                subsystem_name.startswith('WAN')
                            )
                            
                            if is_wan_subsystem:
                                interface_name = (
                                    subsystem.get('interface') or 
                                    subsystem.get('wan_interface') or
                                    subsystem_name
                                )
                                wan_group = subsystem_name.upper() if subsystem_name != 'www' else 'WAN'
                                wan_key = f"{interface_name}_{wan_group}"
                                
                                wan_interfaces[wan_key] = {
                                    'interface_name': interface_name,
                                    'wan_networkgroup': wan_group,
                                    'download': self._safe_float(subsystem.get('xput_down')),
                                    'upload': self._safe_float(subsystem.get('xput_up')),
                                    'ping': self._safe_float(subsystem.get('speedtest_ping')),
                                    'timestamp': None,
                                    'id': None,
                                    'status': subsystem.get('speedtest_status', subsystem.get('status', 'unknown')),
                                    'source_endpoint': endpoint
                                }
                    
                    if wan_interfaces:
                        _LOGGER.info(f"Found {len(wan_interfaces)} WAN interface(s) on Controller platform: {list(wan_interfaces.keys())}")
                        break
                        
            except Exception as e:
                _LOGGER.debug(f"Failed to get multi-WAN data from {endpoint}: {e}")
                continue
        
        # Determine primary WAN more intelligently  
        primary_wan = self._determine_primary_wan_controller(wan_interfaces) if wan_interfaces else None
        
        _LOGGER.info(f"Controller Multi-WAN detection complete: {len(wan_interfaces)} interfaces found, primary: {primary_wan}")
        _LOGGER.debug(f"WAN interfaces found: {list(wan_interfaces.keys())}")
        
        return {
            'wan_interfaces': list(wan_interfaces.values()),
            'total_interfaces': len(wan_interfaces),
            'primary_wan': primary_wan,
            'multi_wan_enabled': True,
            'platform_type': 'controller',
            'detection_method': 'legacy_endpoint_scan'
        }

    def _determine_primary_wan_udm(self, wan_interfaces):
        """Determine primary WAN interface for UDM controllers using routing and configuration data."""
        if not wan_interfaces:
            return None
            
        _LOGGER.debug("Attempting to determine primary WAN for UDM platform")
        
        # Try to get routing information and network configuration
        routing_info = self._get_udm_routing_info()
        network_config = self._get_udm_network_config()
        
        # Method 1: Check routing table for default route
        if routing_info:
            primary_from_routing = self._find_primary_from_routing(routing_info, wan_interfaces)
            if primary_from_routing:
                _LOGGER.info(f"Primary WAN determined from routing table: {primary_from_routing}")
                return primary_from_routing
        
        # Method 2: Check network configuration priorities  
        if network_config:
            primary_from_config = self._find_primary_from_network_config(network_config, wan_interfaces)
            if primary_from_config:
                _LOGGER.info(f"Primary WAN determined from network config: {primary_from_config}")
                return primary_from_config
        
        # Method 3: Look for active connections with actual speed test data
        primary_from_data = self._find_primary_from_speedtest_data(wan_interfaces)
        if primary_from_data:
            _LOGGER.info(f"Primary WAN determined from speedtest data: {primary_from_data}")
            return primary_from_data
            
        # Fallback: Use first interface (existing logic)
        fallback = list(wan_interfaces.keys())[0]
        _LOGGER.warning(f"Could not determine primary WAN intelligently, falling back to first interface: {fallback}")
        return fallback
    
    def _determine_primary_wan_controller(self, wan_interfaces):
        """Determine primary WAN interface for traditional controllers."""
        if not wan_interfaces:
            return None
            
        _LOGGER.debug("Attempting to determine primary WAN for traditional controller")
        
        # Try to get routing and configuration information
        routing_info = self._get_controller_routing_info()
        
        # Method 1: Check routing information
        if routing_info:
            primary_from_routing = self._find_primary_from_routing(routing_info, wan_interfaces)
            if primary_from_routing:
                _LOGGER.info(f"Primary WAN determined from routing: {primary_from_routing}")
                return primary_from_routing
        
        # Method 2: Look for active connections with speed test data
        primary_from_data = self._find_primary_from_speedtest_data(wan_interfaces)
        if primary_from_data:
            _LOGGER.info(f"Primary WAN determined from speedtest data: {primary_from_data}")
            return primary_from_data
        
        # Fallback: Use first interface (existing logic)
        fallback = list(wan_interfaces.keys())[0]
        _LOGGER.warning(f"Could not determine primary WAN intelligently, falling back to first interface: {fallback}")
        return fallback

    def _get_udm_routing_info(self):
        """Get routing information from UDM platform."""
        endpoints_to_try = [
            f"{self.url}/proxy/network/api/s/{self.site}/stat/routes",
            f"{self.url}/proxy/network/api/s/{self.site}/stat/routing",
            f"{self.url}/proxy/network/api/s/{self.site}/rest/routing/table"
        ]
        
        for endpoint in endpoints_to_try:
            try:
                _LOGGER.debug(f"Requesting UDM routing info from: {endpoint}")
                response = self._make_request(self.session.get, endpoint, max_retries=1)
                data = response.json()
                if 'data' in data and data['data']:
                    _LOGGER.debug(f"Successfully retrieved routing info from {endpoint}")
                    return data['data']
            except Exception as e:
                _LOGGER.debug(f"Failed to get routing info from {endpoint}: {e}")
                continue
        
        return None
    
    def _get_udm_network_config(self):
        """Get network configuration from UDM platform."""
        endpoints_to_try = [
            f"{self.url}/proxy/network/api/s/{self.site}/rest/networkconf",
            f"{self.url}/proxy/network/api/s/{self.site}/rest/wanconf"
        ]
        
        for endpoint in endpoints_to_try:
            try:
                _LOGGER.debug(f"Requesting UDM network config from: {endpoint}")
                response = self._make_request(self.session.get, endpoint, max_retries=1)
                data = response.json()
                if 'data' in data and data['data']:
                    _LOGGER.debug(f"Successfully retrieved network config from {endpoint}")
                    return data['data']
            except Exception as e:
                _LOGGER.debug(f"Failed to get network config from {endpoint}: {e}")
                continue
        
        return None
    
    def _get_controller_routing_info(self):
        """Get routing information from traditional controller."""
        endpoints_to_try = [
            f"{self.url}/api/s/{self.site}/stat/routes", 
            f"{self.url}/api/s/{self.site}/stat/routing"
        ]
        
        for endpoint in endpoints_to_try:
            try:
                _LOGGER.debug(f"Requesting controller routing info from: {endpoint}")
                response = self._make_request(self.session.get, endpoint, max_retries=1)
                data = response.json()
                if 'data' in data and data['data']:
                    _LOGGER.debug(f"Successfully retrieved routing info from {endpoint}")
                    return data['data']
            except Exception as e:
                _LOGGER.debug(f"Failed to get routing info from {endpoint}: {e}")
                continue
        
        return None
    
    def _find_primary_from_routing(self, routing_info, wan_interfaces):
        """Find primary WAN from routing table data."""
        try:
            # Look for default route (0.0.0.0/0)
            for route in routing_info:
                network = route.get('network', route.get('destination', ''))
                netmask = route.get('netmask', route.get('mask', ''))
                interface = route.get('interface', route.get('dev', ''))
                
                # Check if this is a default route
                if (network in ['0.0.0.0', 'default'] and netmask in ['0.0.0.0', '0']):
                    # Find matching WAN interface
                    for wan_key, wan_data in wan_interfaces.items():
                        wan_interface = wan_data.get('interface_name', '')
                        if wan_interface and interface and (
                            interface == wan_interface or 
                            interface.startswith(wan_interface) or
                            wan_interface.startswith(interface)
                        ):
                            _LOGGER.debug(f"Found default route via interface {interface} matching WAN {wan_interface}")
                            return wan_key
                            
            # Look for routes with highest priority or lowest metric
            default_routes = []
            for route in routing_info:
                network = route.get('network', route.get('destination', ''))
                if network in ['0.0.0.0', 'default']:
                    default_routes.append(route)
            
            if default_routes:
                # Sort by metric (lower is better) or priority
                default_routes.sort(key=lambda r: r.get('metric', r.get('priority', 9999)))
                best_route = default_routes[0]
                interface = best_route.get('interface', best_route.get('dev', ''))
                
                for wan_key, wan_data in wan_interfaces.items():
                    wan_interface = wan_data.get('interface_name', '')
                    if wan_interface and interface and interface.startswith(wan_interface):
                        _LOGGER.debug(f"Found best metric default route via {interface}")
                        return wan_key
                        
        except Exception as e:
            _LOGGER.debug(f"Error parsing routing info: {e}")
            
        return None
    
    def _find_primary_from_network_config(self, network_config, wan_interfaces):
        """Find primary WAN from network configuration."""
        try:
            # Look for WAN configuration with primary designation
            for config in network_config:
                purpose = config.get('purpose', '').lower()
                if 'wan' in purpose:
                    interface = config.get('interface', config.get('name', ''))
                    is_primary = config.get('is_primary', config.get('primary', False))
                    wan_type = config.get('wan_type', config.get('type', ''))
                    
                    # Check if explicitly marked as primary
                    if is_primary:
                        for wan_key, wan_data in wan_interfaces.items():
                            wan_interface = wan_data.get('interface_name', '')
                            if wan_interface and interface and (
                                interface == wan_interface or 
                                interface.startswith(wan_interface)
                            ):
                                _LOGGER.debug(f"Found primary WAN from config: {interface}")
                                return wan_key
                    
                    # Check for WAN type priorities (dhcp vs pppoe vs static)
                    if wan_type == 'dhcp' and interface:
                        for wan_key, wan_data in wan_interfaces.items():
                            wan_interface = wan_data.get('interface_name', '')
                            if wan_interface and interface.startswith(wan_interface):
                                _LOGGER.debug(f"Found DHCP WAN interface: {interface}")
                                return wan_key
                                
        except Exception as e:
            _LOGGER.debug(f"Error parsing network config: {e}")
            
        return None
    
    def _find_primary_from_speedtest_data(self, wan_interfaces):
        """Find primary WAN based on which interface has the most recent speed test data."""
        try:
            wan_with_data = []
            
            for wan_key, wan_data in wan_interfaces.items():
                download = wan_data.get('download')
                upload = wan_data.get('upload')
                timestamp = wan_data.get('timestamp')
                
                # Score based on having data and recency
                score = 0
                if download is not None and download > 0:
                    score += 10
                if upload is not None and upload > 0:
                    score += 10
                if timestamp:
                    score += 5
                
                if score > 0:
                    wan_with_data.append((wan_key, score, timestamp))
            
            if wan_with_data:
                # Sort by score (descending) then by timestamp (most recent first)
                wan_with_data.sort(key=lambda x: (x[1], x[2] or 0), reverse=True)
                primary_wan = wan_with_data[0][0]
                _LOGGER.debug(f"Found primary WAN from speed test data: {primary_wan}")
                return primary_wan
                
        except Exception as e:
            _LOGGER.debug(f"Error finding primary from speedtest data: {e}")
            
        return None

    def _safe_float(self, value):
        """Safely convert value to float"""
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

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