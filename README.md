[![Sponsor Me](https://img.shields.io/badge/Sponsor%20Me-%F0%9F%92%AA-purple?style=for-the-badge)](https://github.com/sponsors/biofects?frequency=recurring&sponsor=biofects)


# 🌐 UniFi Speedtest for Home Assistant
# I will be pushing updates soon, sorry all i have been away for a while

## 🔍 About

This Home Assistant custom integration provides real-time speed test monitoring for UniFi networks with **enhanced dual WAN support**. It supports all UniFi platforms including UDM Pro, UDM SE, Cloud Key, and traditional UniFi Controller software, allowing you to track download speed, upload speed, and ping directly within Home Assistant.

**🆕 v2.2.0: Smart Controller Detection** - User-controlled controller type selection with intelligent entity creation based on actual WAN connections.

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
[![GitHub Release](https://img.shields.io/github/v/release/biofects/HA-Unifi-Speedtest?style=flat-square)](https://github.com/biofects/HA-Unifi-Speedtest/releases)
[![GitHub Last Commit](https://img.shields.io/github/last-commit/biofects/HA-Unifi-Speedtest?style=flat-square)](https://github.com/biofects/HA-Unifi-Speedtest/commits/main)
[![GitHub Issues](https://img.shields.io/github/issues/biofects/HA-Unifi-Speedtest?style=flat-square)](https://github.com/biofects/HA-Unifi-Speedtest/issues)
[![License](https://img.shields.io/github/license/biofects/HA-Unifi-Speedtest?style=flat-square)](https://github.com/biofects/HA-Unifi-Speedtest/blob/main/LICENSE)

---
## 💸 Donations Appreciated!
If you find this plugin useful, please consider donating. Your support is greatly appreciated!

### Sponsor me on GitHub
[![Sponsor Me](https://img.shields.io/badge/Sponsor%20Me-%F0%9F%92%AA-purple?style=for-the-badge)](https://github.com/sponsors/biofects?frequency=recurring&sponsor=biofects) 

### or
## Paypal

[![paypal](https://www.paypalobjects.com/en_US/i/btn/btn_donateCC_LG.gif)](https://www.paypal.com/cgi-bin/webscr?cmd=_s-xclick&hosted_button_id=TWRQVYJWC77E6)
---


---

## ✨ Features

- **� Smart Controller Detection**: User-controlled selection between UDM and traditional controller types
- **� Intelligent WAN Management**: UDM controllers automatically detect multiple WANs, traditional controllers use single WAN
- **📊 Connection-Based Entities**: Only creates entities for actually connected WAN interfaces  
- **🔧 Universal Compatibility**: Works with UDM Pro, UDM SE, UDM Base, Cloud Key Gen2+, and traditional UniFi Controllers
- **� Real-time Metrics**: Monitor download speeds, upload speeds, and network latency (ping) for each connected WAN
- **🚀 Speed Test Initiation**: Start speed tests remotely via Home Assistant (traditional controllers)
- **🏠 Home Assistant Integration**: Full integration with automations, scripts, and dashboards
- **⚙️ Clean Naming**: Smart entity names based on number of connected WANs (single WAN gets clean names)
- **🔒 Reliable Authentication**: Fixed endpoint selection prevents 401/404 errors

## 📸 Screenshots

### Configuration
Configure multi-WAN support during setup to enable separate monitoring for each WAN interface:

![Multi-WAN Configuration](images/configwan.png)

### Dual WAN Monitoring in Action
See how the integration creates separate sensors for each WAN interface, providing individual speed metrics:

#### WAN 1 Sensors
Monitor your primary WAN connection with dedicated sensors for download, upload, and ping:

![WAN 1 Sensors](images/wan1.png)

#### WAN 2 Sensors  
Track your secondary WAN connection independently with its own set of performance metrics:

![WAN 2 Sensors](images/wan2.png)

*Notice how each WAN interface gets its own sensors, solving the issue where dual WAN setups previously showed identical speeds for both connections.*

## 🏗 Supported Systems

### ✅ UDM Pro / UDM SE
- **Multi-WAN Support**: ✅ Full dual WAN detection and monitoring
- **Speed Test Monitoring**: ✅ Automatic retrieval of speed test results
- **Separate Sensors**: ✅ Individual sensors for each WAN interface
- **URL Format**: `https://udm-ip` (port 443)

### ✅ UDM Base
- **Multi-WAN Support**: ❌ Single WAN hardware limitation
- **Speed Test Monitoring**: ✅ Standard monitoring for single WAN
- **Backward Compatible**: ✅ Works exactly as before
- **URL Format**: `https://udm-ip` (port 443)

### ✅ Cloud Key Gen2+ with Multi-WAN Gateway
- **Multi-WAN Support**: ✅ Depends on gateway model (USG Pro 4, UXG Pro)
- **Speed Test Monitoring**: ✅ Full functionality
- **API Support**: ✅ Modern UniFi OS endpoints
- **URL Format**: `https://cloudkey-ip` (port 443)

### ✅ Traditional UniFi Controller Software
- **Multi-WAN Support**: ⚠️ Depends on gateway hardware
- **Speed Test Monitoring**: ✅ Full functionality including API-initiated tests
- **Legacy Support**: ✅ Enhanced compatibility with older API structures
- **URL Format**: `https://controller-ip:8443`

## 🚀 Installation

### HACS Installation (Recommended)

1. Open HACS in your Home Assistant instance
2. Click on "Integrations"
3. Click the three dots in the top right corner
4. Select "Custom repositories"
5. Add this repository URL
6. Select "Integration" as the category
7. Click "Add"
8. Find "HA Unifi Speedtest" in the integration list
9. Click "Download"
10. Restart Home Assistant

### Manual Installation

1. Download the latest release
2. Copy the `custom_components/ha_unifi_speedtest` directory to your Home Assistant's `custom_components` directory
3. Restart Home Assistant

## ⚙ Configuration

1. Go to Configuration > Integrations
2. Click "+" to add a new integration
3. Search for "HA Unifi Speedtest"
4. Enter the following details:
   - **URL**: Your UniFi Controller URL
     - UDM Pro/SE: `https://udm-ip`
     - Cloud Key Gen2+: `https://cloudkey-ip`
     - Traditional Controller: `https://controller-ip:8443`
   - **Username**: UniFi Controller admin username
   - **Password**: UniFi Controller admin password
   - **Controller Type**: Select your controller type  
     - **UDM Pro/SE/Cloud Key Gen2+** - for UniFi OS devices (supports multi-WAN detection)
     - **Self-hosted Controller** - for traditional UniFi Controller software (single WAN mode)
   - **Site** (Optional): Site name (default: "default")
   - **SSL Verification** (Optional): Enable/disable SSL certificate verification
   - **Multi-WAN Detection**: Automatically enabled for UDM controllers, disabled for traditional controllers
   - **Enable Automatic Speed Tests**: Schedule regular speed tests
   - **Speed Test Interval**: How often to run automatic tests (15-1440 minutes)

📋 **See the [Screenshots](#-screenshots) section above for visual examples of the configuration process and resulting sensors.**

## 📡 Sensors

### Single WAN Setup
The integration creates three sensors for monitoring network performance:

- **UniFi Speed Test Download Speed** (Mbit/s)
- **UniFi Speed Test Upload Speed** (Mbit/s)  
- **UniFi Speed Test Ping** (ms)

### 🆕 Dual WAN Setup
For multi-WAN configurations, separate sensors are created for each WAN interface:

**WAN 1:**
- **UniFi Speed Test Download Speed WAN** (Mbit/s)
- **UniFi Speed Test Upload Speed WAN** (Mbit/s)  
- **UniFi Speed Test Ping WAN** (ms)

**WAN 2:**
- **UniFi Speed Test Download Speed WAN2** (Mbit/s)
- **UniFi Speed Test Upload Speed WAN2** (Mbit/s)  
- **UniFi Speed Test Ping WAN2** (ms)

### Additional Sensors
- **UniFi Speed Test Runs**: Track total number of speed tests performed
- **UniFi API Health**: Monitor integration connection status

### 🏷️ Sensor Attributes

Each multi-WAN sensor includes additional attributes:
- `interface_name`: Physical interface (e.g., "eth9", "eth10")
- `wan_networkgroup`: WAN group name (e.g., "WAN", "WAN2")
- `wan_number`: Sequential WAN number
- `total_wan_interfaces`: Total detected WAN interfaces
- `is_primary_wan`: Boolean indicating primary WAN (intelligently determined from routing/config)
- `timestamp`: Last speedtest timestamp
- `status`: Interface status

**Note on `is_primary_wan`**: This attribute now reflects the **actual** primary WAN as configured in your UniFi controller, not just the first physical port detected. If you've configured a secondary port (like SFP+ port 2) as your primary WAN, that interface will correctly show `is_primary_wan: true`.

## 🔧 Services

### `ha_unifi_speedtest.start_speed_test`

Initiates a speed test on your UniFi network.

**Note**: Only available for traditional UniFi Controller software. UDM Pro users must start speed tests manually via the UniFi Network web interface.

#### Example Usage:

**In Automations:**
```yaml
action:
  - service: ha_unifi_speedtest.start_speed_test
```

**In Scripts:**
```yaml
test_network_speed:
  sequence:
    - service: ha_unifi_speedtest.start_speed_test
    - delay: "00:02:00"  # Wait for test to complete
    - service: notify.mobile_app
      data:
        message: "Speed test completed. Download: {{ states('sensor.unifi_speed_test_download_speed') }} Mbps"
```

**Lovelace Button:**
```yaml
type: button
name: Start Speed Test
tap_action:
  action: call-service
  service: ha_unifi_speedtest.start_speed_test
```

### `ha_unifi_speedtest.get_speed_test_status`

Manually refreshes speed test data from your UniFi controller.

## 📊 Example Dashboard

```yaml
type: entities
title: Network Speed Test
entities:
  - entity: sensor.unifi_speed_test_download_speed
    name: Download Speed
  - entity: sensor.unifi_speed_test_upload_speed  
    name: Upload Speed
  - entity: sensor.unifi_speed_test_ping
    name: Ping
```

# HA UniFi Speedtest v2.0.1 - Update Notes

## 🆕 What's New in v2.1.1 (Latest)
### 🐛 **Bug Fixes**
- **UDM Pro Compatibility**: Fixed 404 errors on UDM Pro devices that don't support advanced routing endpoints
- **Graceful Fallback**: Integration now automatically detects unsupported UDM routing endpoints and switches to controller mode
- **Cleaner Logs**: Eliminated repetitive 404 error messages during setup
- **Improved Stability**: Better error handling prevents integration setup failures

## 🆕 What's New in v2.1.0
### ✅ **Intelligent Primary WAN Detection** 
- **Smart Primary WAN Detection**: Now properly identifies the primary WAN interface based on routing tables and network configuration
- **Resolves Dual WAN Issues**: Fixes issues where secondary physical ports configured as primary WAN showed incorrect "is_primary_wan" status  
- **Multiple Detection Methods**: Uses routing table analysis, network configuration, and speed test data to determine the true primary WAN
- **Smart Device Naming**: Automatically names devices and sensors as "Primary WAN" and "Secondary WAN" for clarity
- **Backward Compatible**: Falls back to previous behavior if advanced detection fails

### ✅ **Enhanced User Experience**
- **Clear Device Names**: Devices now show as "Primary WAN" and "Secondary WAN" instead of "WAN" and "WAN2"
- **Improved Sensor Names**: Sensors clearly indicate which is primary vs secondary
- **Better Attributes**: Enhanced sensor attributes show primary WAN status and interface details

## 🆕 What's New in v2.2.0

### ✅ **User-Controlled Controller Type Selection**
- **No More Auto-Detection**: Eliminated confusing automatic controller detection that could misidentify your setup
- **Clear Controller Options**: Choose between "UDM Pro/SE/Cloud Key Gen2+" or "Self-hosted Controller"  
- **Reliable Endpoint Selection**: Always uses the correct API endpoints for your controller type
- **Fixed Authentication Issues**: Resolved 401/404 errors caused by incorrect endpoint detection

### ✅ **Intelligent WAN Interface Management**
- **UDM Multi-WAN Logic**: UDM controllers automatically check for multiple WAN connections
- **Connection-Based Entity Creation**: Only creates entities for actually connected WAN interfaces
- **Clean Single WAN Naming**: When only one WAN is connected, gets clean names like "Download Speed" instead of "Download Speed WAN1"
- **Traditional Controller Single WAN**: Self-hosted controllers use single WAN mode with appropriate endpoints

### ✅ **Enhanced User Experience**  
- **Eliminated Unknown Entities**: No more persistent "Unknown" entities that couldn't be removed
- **Better Configuration UI**: Clear descriptions help you choose the right controller type
- **Improved Error Messages**: More helpful messages when no speedtest data is available
- **Predictable Behavior**: Integration behaves consistently based on your controller type selection

### ✅ **Previous Updates (v1.4.0)**
- **Added Poll Control**: Configurable poll interval
- **Fixed Compatibility Issues**: Resolved UDM and Software-based controller issues
- **Adjusted Initial Run Time**: Corrected initial run timing for software controllers
- **Manual Speed Test Button**: Added on-demand speed test capability

### ✅ **Manual Speed Test Button**
Add this button to your dashboard for on-demand speed tests:

```yaml
show_name: true
show_icon: true
type: button
name: Start Speed Test
icon: mdi:speedometer
tap_action:
  action: call-service
  service: ha_unifi_speedtest.start_speed_test
```

## 📊 Available Sensors

- **UniFi Speed Test Download Speed** - Download speed in `Mbit/s`
- **UniFi Speed Test Upload Speed** - Upload speed in `Mbit/s`  
- **UniFi Speed Test Ping** - Latency in `ms`

## 🔧 Compatibility

- ✅ **UDM Pro / UDM SE / Cloud Key** - Full support with automatic speed test triggering
- ✅ **Traditional UniFi Controller Software** - Full support
- ✅ **Both controller types** get fresh speed test data every hour automatically

## 🚀 Quick Setup

1. **Install Integration**: Add via HACS or copy files to `custom_components/ha_unifi_speedtest/`
2. **Configure**: Settings → Devices & Services → Add Integration → "HA Unifi Speedtest"
3. **Enter Details**: Your UniFi controller URL, username, password, and controller type
4. **Done!**: Sensors will appear automatically with hourly speed tests

---

*The integration now works seamlessly with both UDM Pro and traditional UniFi Controllers, providing regular speed test data with proper Home Assistant unit standards.*

## 🔧 Troubleshooting

### Common Issues

**403 Forbidden Error**: 
- Verify your username/password are correct
- Ensure the user account has admin privileges
- For UDM Pro: Disable 2FA temporarily or create a local admin user

**Connection Refused**:
- Check the URL format matches your controller type
- Verify the controller is accessible from Home Assistant
- Check firewall settings

**No Speed Test Data**:
- Ensure at least one speed test has been run on your controller
- Traditional controllers: Use the `start_speed_test` service
- UDM Pro: Run a speed test via the web interface first

### Primary WAN Detection Issues

The integration now uses **intelligent primary WAN detection** to properly identify which WAN interface is actually your primary connection, even if you've configured a secondary port (like SFP+ port 2) as your primary WAN.

**Primary WAN Detection Methods** (in order of priority):
1. **Routing Table Analysis**: Checks the default route (0.0.0.0/0) to identify which interface handles the primary traffic
2. **Network Configuration**: Looks for explicitly configured primary WAN settings in the UniFi controller
3. **Speed Test Data**: Uses the WAN interface with the most recent and complete speed test data
4. **Fallback**: Uses the first detected interface (legacy behavior)

**If Primary WAN Detection is Incorrect**:

1. **Check UniFi Network Settings**: 
   - Verify that your desired primary WAN is correctly configured in the UniFi Network application
   - Ensure the routing table reflects your intended primary WAN

2. **Check Integration Logs**:
   - Enable debug logging (see below)
   - Look for messages like: "Primary WAN determined from routing table: eth9_WAN"
   - The logs will show which detection method was used

3. **Check Sensor Attributes**:
   - Go to Developer Tools > States
   - Find your UniFi speed test sensors
   - Check if `is_primary_wan` is correct on your configured primary WAN

**Expected Behavior**:
- The WAN interface you've configured as primary in UniFi should show `is_primary_wan: true`
- That interface should have the speed test results
- Other WAN interfaces should show `is_primary_wan: false`
- Devices and sensors will be named "Primary WAN" and "Secondary WAN"

### Debug Logging

To enable debug logging, add the following to your `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.ha_unifi_speedtest: debug
```

## 🤝 Contributing

Feel free to contribute to this project. Please read the contributing guidelines before making a pull request.

## 📜 License

This project is licensed under the MIT License - see the LICENSE file for details.

## ⚖ Disclaimer

This integration is not affiliated with Ubiquiti Inc. or UI.com. All product names, logos, and brands are property of their respective owners.

[releases-shield]: https://img.shields.io/github/release/tfam/ha_unifi_speedtest.svg
[releases]: https://github.com/tfam/ha_unifi_speedtest/releases
[maintenance-shield]: https://img.shields.io/maintenance/yes/2024.svg

