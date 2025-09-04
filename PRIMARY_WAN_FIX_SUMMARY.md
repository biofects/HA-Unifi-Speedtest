# Primary WAN Detection Enhancement - Summary

## Problem Addressed

The user reported that their UniFi integration showed incorrect primary WAN identification. Specifically:
- Their WAN connection is plugged into the secondary WAN port (SFP+ port 2)
- They configured this SFP+ port as the primary WAN in UniFi Network settings
- However, the HA integration showed `is_primary_wan: false` for this interface
- The other WAN port showed `is_primary_wan: true` but had no speed test results

## Root Cause

The previous implementation used overly simplistic logic:
```python
'primary_wan': list(wan_interfaces.keys())[0] if wan_interfaces else None
```

This just took the **first** WAN interface discovered, which doesn't reflect the actual network configuration.

## Solution Implemented

### 1. Intelligent Primary WAN Detection
Replaced the simple logic with a multi-method approach that checks (in order):

1. **Routing Table Analysis** - Checks the default route (0.0.0.0/0) to see which interface handles primary traffic
2. **Network Configuration** - Looks for explicit primary WAN designations in UniFi settings  
3. **Speed Test Data Analysis** - Uses the interface with the most recent and complete speed test data
4. **Fallback** - Uses the original logic if all else fails

### 2. Enhanced API Methods
Added new methods to gather routing and configuration data:

**For UDM Controllers:**
- `_get_udm_routing_info()` - Retrieves routing table
- `_get_udm_network_config()` - Gets network configuration
- `_determine_primary_wan_udm()` - Intelligently determines primary WAN

**For Traditional Controllers:**
- `_get_controller_routing_info()` - Retrieves routing table  
- `_determine_primary_wan_controller()` - Intelligently determines primary WAN

### 3. Improved Sensor Logic
Enhanced the sensor's `is_primary_wan` attribute determination with multiple matching strategies:
- Direct key matching
- Interface name matching  
- Position-based fallback

### 4. Debugging Tools
Created `debug_primary_wan.py` script that:
- Tests API connectivity
- Shows all WAN interfaces detected
- Displays routing and configuration information
- Reveals which detection method was used
- Provides full diagnostic output

## Files Modified

1. **`api.py`**:
   - Added intelligent primary WAN detection methods
   - Enhanced logging for WAN detection process
   - Added routing and configuration data retrieval

2. **`sensor.py`**:
   - Improved `_determine_is_primary_wan()` method
   - Enhanced sensor attribute logic

3. **`manifest.json`**:
   - Updated version to 2.1.0

4. **`README.md`**:
   - Added troubleshooting section for primary WAN issues
   - Updated features and changelog
   - Documented the new detection methods

5. **New Files**:
   - `debug_primary_wan.py` - Diagnostic script
   - `CHANGELOG.md` - Formal changelog

## Expected Behavior After Update

1. **Correct Primary WAN Identification**: The interface configured as primary in UniFi Network settings will show `is_primary_wan: true`

2. **Speed Test Data on Correct Interface**: Speed test results should appear on the interface that's actually being used for internet traffic

3. **Detailed Logging**: Debug logs will show which method was used to determine the primary WAN:
   - "Primary WAN determined from routing table: eth9_WAN"
   - "Primary WAN determined from network config: eth9_WAN"  
   - "Primary WAN determined from speedtest data: eth9_WAN"

4. **Backward Compatibility**: If the new detection methods fail, it falls back to the original behavior

## Testing the Fix

Users can test the enhancement using the debug script:

```bash
cd /path/to/integration
python3 debug_primary_wan.py https://your-udm-ip username password
```

This will show:
- Which WAN interfaces are detected
- What the routing table contains
- Which interface is identified as primary
- Which detection method was successful

## Upgrade Instructions

1. Replace the integration files with the updated versions
2. Restart Home Assistant
3. Check the integration logs for primary WAN detection messages
4. Verify that `is_primary_wan` attributes are now correct
5. If issues persist, run the debug script for troubleshooting

The fix maintains full backward compatibility while significantly improving primary WAN detection accuracy for complex dual-WAN configurations.
