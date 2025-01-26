# 🌐 UniFi Site Manager for Home Assistant

## 🔍 About

This Home Assistant custom integration provides real-time speed test monitoring for UniFi networks. It allows you to track download speed, upload speed, and ping directly within Home Assistant.

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
[![GitHub Release][releases-shield]][releases]
![Project Maintenance][maintenance-shield]

## 💸 Donations Welcome!

If you find this integration useful, please consider donating. Your support is greatly appreciated!

[![paypal](https://www.paypalobjects.com/en_US/i/btn/btn_donateCC_LG.gif)](https://www.paypal.com/cgi-bin/webscr?cmd=_s-xclick&hosted_button_id=TWRQVYJWC77E6)

---

## ✨ Features

- Retrieve network speed test results
- Monitor download and upload speeds
- Track network latency (ping)


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
    5. URL of your UniFi UDM
    6. Username
    7. Password
    8. (Optional) Site name
    9. (Optional) SSL Verification

## 📡 Sensors

### Site Sensor
- The integration creates three sensors:
    - Download Speed (Mbps)
    - Upload Speed (Mbps)
    - Ping (ms)





## 🔧 Debugging

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
