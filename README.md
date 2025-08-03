[![Sponsor Me](https://img.shields.io/badge/Sponsor%20Me-%F0%9F%92%AA-purple?style=for-the-badge)](https://github.com/sponsors/biofects?frequency=recurring&sponsor=biofects)


# 🌐 UniFi Speedtest for Home Assistant

## 🔍 About

This Home Assistant custom integration provides real-time speed test monitoring for UniFi networks. It supports both traditional UniFi Controller software and UDM Pro/Cloud Key setups, allowing you to track download speed, upload speed, and ping directly within Home Assistant.

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
[![GitHub Release][releases-shield]][releases]
![Project Maintenance][maintenance-shield]

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

- **Dual Controller Support**: Works with both traditional UniFi Controller software and UDM Pro/Cloud Key
- **Speed Test Monitoring**: Retrieve network speed test results automatically
- **Real-time Metrics**: Monitor download speeds, upload speeds, and network latency (ping)
- **Speed Test Initiation**: Start speed tests remotely via Home Assistant (traditional controllers only)
- **Home Assistant Services**: Integrate with automations and scripts

## 🏗️ Supported Systems

### ✅ Traditional UniFi Controller Software
- **Full functionality** including API-initiated speed tests
- Typically runs on dedicated hardware or Cloud Key Gen1
- URL format: `https://controller-ip:8443`

### ✅ UDM Pro/Cloud Key Gen2+
- **Speed test result monitoring** (reading existing test data)
- Speed tests must be initiated manually via UniFi Network web interface
- URL format: `https://udm-ip` (port 443)

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

## ⚙️ Configuration

1. Go to Configuration > Integrations
2. Click "+" to add a new integration
3. Search for "HA Unifi Speedtest"
4. Enter the following details:
   - **URL**: Your UniFi Controller URL
     - Traditional Controller: `https://controller-ip:8443`
     - UDM Pro: `https://udm-ip`
   - **Username**: UniFi Controller admin username
   - **Password**: UniFi Controller admin password
   - **Controller Type**: Select your controller type
     - `udm` - for UDM Pro, UDM, Cloud Key Gen2+
     - `controller` - for traditional UniFi Controller software
   - **Site** (Optional): Site name (default: "default")
   - **SSL Verification** (Optional): Enable/disable SSL certificate verification

## 📡 Sensors

The integration creates three sensors for monitoring network performance:

- **UniFi Speed Test Download Speed** (Mbps)
- **UniFi Speed Test Upload Speed** (Mbps)  
- **UniFi Speed Test Ping** (ms)

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

## ⚖️ Disclaimer

This integration is not affiliated with Ubiquiti Inc. or UI.com. All product names, logos, and brands are property of their respective owners.

[releases-shield]: https://img.shields.io/github/release/tfam/ha_unifi_speedtest.svg
[releases]: https://github.com/tfam/ha_unifi_speedtest/releases
[maintenance-shield]: https://img.shields.io/maintenance/yes/2024.svg
