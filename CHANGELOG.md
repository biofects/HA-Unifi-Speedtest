# Changelog

All notable changes to this project will be documented in this file.

## [2.1.0] - 2025-09-04

### Added
- **Intelligent Primary WAN Detection**: Enhanced logic to properly identify the primary WAN interface based on routing configuration rather than just physical port order
- **Smart Device and Sensor Naming**: Devices and sensors now automatically display as "Primary WAN" and "Secondary WAN" for clarity
- **Enhanced Sensor Attributes**: Added `is_primary_wan` attribute to clearly indicate which WAN is primary

### Fixed
- **Primary WAN Misidentification**: Resolves issue where secondary physical ports configured as primary WAN in UniFi showed incorrect `is_primary_wan: false` status
- **Dual WAN Configuration Issues**: Now properly handles configurations where SFP+ ports or other secondary physical ports are configured as the primary WAN

### Changed
- **Improved User Experience**: Device and sensor names now clearly indicate "Primary WAN" vs "Secondary WAN"
- **Better Detection Logic**: Uses routing tables, network configuration, and speed test data to determine actual primary WAN
- **Enhanced Logging**: More detailed logging for WAN detection process

## [2.0.1] - Previous Release

### Added
- Multi-WAN support with automatic detection
- Separate sensors for each WAN interface
- Universal compatibility across all UniFi controller types
- Configurable polling intervals
- Enhanced error handling and rate limiting

### Fixed
- Dual WAN detection issues
- Controller compatibility problems
- Speed test data retrieval inconsistencies

## [1.4.0] - Previous Release

### Added
- Manual speed test initiation
- Configurable polling intervals
- Improved controller compatibility

### Fixed
- Initial run timing issues
- UDM compatibility problems
