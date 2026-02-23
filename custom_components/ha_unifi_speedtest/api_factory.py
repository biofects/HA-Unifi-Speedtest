"""Factory for creating the appropriate UniFi API client based on controller type."""
import logging
from typing import Optional

try:
    from .api_hardware import UniFiHardwareAPI
    from .api_software import UniFiSoftwareAPI
except ImportError:
    from api_hardware import UniFiHardwareAPI
    from api_software import UniFiSoftwareAPI

_LOGGER = logging.getLogger(__name__)


def create_unifi_api(
    url: str,
    controller_type: str = "udm",
    username: Optional[str] = None,
    password: Optional[str] = None,
    api_key: Optional[str] = None,
    site: str = "default",
    verify_ssl: bool = False,
    enable_multi_wan: bool = True,
):
    """Create appropriate UniFi API client based on controller type and credentials.
    
    Args:
        url: Controller URL
        controller_type: 'udm' for hardware or 'controller' for software
        username: Username for software controller
        password: Password for software controller
        api_key: API key for hardware controller
        site: Site name/ID
        verify_ssl: Whether to verify SSL certificates
        enable_multi_wan: Enable multi-WAN support
        
    Returns:
        UniFiHardwareAPI or UniFiSoftwareAPI instance
        
    Raises:
        ValueError: If required credentials are missing for the controller type
    """
    _LOGGER.info(f"Creating UniFi API client for controller type: {controller_type}")
    
    if controller_type == "udm":
        # UDM/UniFi OS Hardware - requires API key
        if not api_key:
            raise ValueError(
                "API key is required for UDM/UniFi OS hardware controllers. "
                "Generate one in Settings → Admins → [Your Admin] → API Key."
            )
        _LOGGER.info("Creating UniFi Hardware API client (API key authentication)")
        return UniFiHardwareAPI(
            url=url,
            api_key=api_key,
            site=site,
            verify_ssl=verify_ssl,
            enable_multi_wan=enable_multi_wan,
        )
    
    elif controller_type == "controller":
        # Self-hosted Software Controller - requires username/password
        if not username or not password:
            raise ValueError(
                "Username and password are required for self-hosted software controllers. "
                "Use your local admin account credentials (not UniFi Cloud account)."
            )
        _LOGGER.info("Creating UniFi Software API client (session authentication)")
        return UniFiSoftwareAPI(
            url=url,
            username=username,
            password=password,
            site=site,
            verify_ssl=verify_ssl,
            enable_multi_wan=enable_multi_wan,
        )
    
    else:
        raise ValueError(
            f"Unknown controller type: {controller_type}. "
            f"Supported types: 'udm' (hardware) or 'controller' (software)"
        )


# Backward compatibility: Keep the old UniFiAPI name
def UniFiAPI(
    url: str,
    username: Optional[str] = None,
    password: Optional[str] = None,
    api_key: Optional[str] = None,
    site: str = "default",
    verify_ssl: bool = False,
    controller_type: str = "udm",
    enable_multi_wan: bool = True,
):
    """Legacy UniFiAPI interface for backward compatibility.
    
    Automatically routes to the appropriate API client based on credentials.
    """
    return create_unifi_api(
        url=url,
        controller_type=controller_type,
        username=username,
        password=password,
        api_key=api_key,
        site=site,
        verify_ssl=verify_ssl,
        enable_multi_wan=enable_multi_wan,
    )
