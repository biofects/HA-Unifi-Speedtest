#!/usr/bin/env python3
"""
Debug script to test primary WAN detection logic.
This script helps identify issues with primary WAN detection in UniFi multi-WAN setups.
"""

import sys
import json
import logging
from custom_components.ha_unifi_speedtest.api import UniFiAPI

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    """Main debug function."""
    if len(sys.argv) < 4:
        print("Usage: python3 debug_primary_wan.py <url> <username> <password> [site] [controller_type]")
        print("Example: python3 debug_primary_wan.py https://192.168.1.1 admin password default udm")
        sys.exit(1)
    
    url = sys.argv[1]
    username = sys.argv[2] 
    password = sys.argv[3]
    site = sys.argv[4] if len(sys.argv) > 4 else 'default'
    controller_type = sys.argv[5] if len(sys.argv) > 5 else 'udm'
    
    print(f"Testing UniFi API connection:")
    print(f"  URL: {url}")
    print(f"  Username: {username}")
    print(f"  Site: {site}")
    print(f"  Controller Type: {controller_type}")
    print("-" * 50)
    
    try:
        # Create API instance
        api = UniFiAPI(
            url=url,
            username=username,
            password=password,
            site=site,
            controller_type=controller_type,
            enable_multi_wan=True,
            verify_ssl=False
        )
        
        # Test login
        print("Testing login...")
        api.login()
        print("✓ Login successful")
        
        # Get speed test status
        print("\nTesting multi-WAN speed test status...")
        result = api.get_speed_test_status()
        
        print(f"\nResults:")
        print(f"  Platform: {result.get('platform_type', 'unknown')}")
        print(f"  Total WAN interfaces: {result.get('total_interfaces', 0)}")
        print(f"  Primary WAN: {result.get('primary_wan', 'not determined')}")
        print(f"  Detection method: {result.get('detection_method', 'unknown')}")
        
        # Display detailed WAN interface information
        wan_interfaces = result.get('wan_interfaces', [])
        if wan_interfaces:
            print(f"\nDetailed WAN Interface Information:")
            for i, wan in enumerate(wan_interfaces):
                print(f"\n  WAN {i+1}:")
                print(f"    Interface: {wan.get('interface_name', 'unknown')}")
                print(f"    Group: {wan.get('wan_networkgroup', 'unknown')}")
                print(f"    Download: {wan.get('download', 'N/A')} Mbps")
                print(f"    Upload: {wan.get('upload', 'N/A')} Mbps") 
                print(f"    Ping: {wan.get('ping', 'N/A')} ms")
                print(f"    Status: {wan.get('status', 'unknown')}")
                print(f"    Timestamp: {wan.get('timestamp', 'N/A')}")
                print(f"    Source: {wan.get('source_endpoint', 'unknown')}")
        else:
            print("\n  No WAN interfaces detected!")
        
        # Test routing info (diagnostic)
        print(f"\n" + "="*50)
        print("DIAGNOSTIC INFORMATION")
        print("="*50)
        
        if controller_type == 'udm':
            print("\nTesting UDM routing info...")
            routing_info = api._get_udm_routing_info()
            if routing_info:
                print(f"✓ Retrieved routing info ({len(routing_info)} entries)")
                for route in routing_info[:5]:  # Show first 5 routes
                    print(f"  Route: {route.get('network', 'N/A')}/{route.get('netmask', 'N/A')} via {route.get('interface', 'N/A')}")
            else:
                print("✗ No routing info available")
            
            print("\nTesting UDM network config...")
            network_config = api._get_udm_network_config()
            if network_config:
                print(f"✓ Retrieved network config ({len(network_config)} entries)")
                for config in network_config:
                    purpose = config.get('purpose', 'unknown')
                    if 'wan' in purpose.lower():
                        print(f"  WAN Config: {config.get('name', 'N/A')} - {purpose} - Primary: {config.get('is_primary', config.get('primary', 'N/A'))}")
            else:
                print("✗ No network config available")
        else:
            print("\nTesting Controller routing info...")
            routing_info = api._get_controller_routing_info()
            if routing_info:
                print(f"✓ Retrieved routing info ({len(routing_info)} entries)")
                for route in routing_info[:5]:
                    print(f"  Route: {route.get('network', 'N/A')}/{route.get('netmask', 'N/A')} via {route.get('interface', 'N/A')}")
            else:
                print("✗ No routing info available")
        
        print(f"\nFull API Response (JSON):")
        print(json.dumps(result, indent=2, default=str))
        
    except Exception as e:
        print(f"✗ Error: {e}")
        logger.exception("Full error details:")
        sys.exit(1)

if __name__ == "__main__":
    main()
