# Changelog

All notable changes to this project will be documented in this file.

## [2.2.0] - 2025-10-17

### Added
- **Interface-Specific Testing**: Added `interface_name` parameter to `start_speed_test` service for testing specific WAN interfaces
- **WAN Interface Detection Service**: New `get_wan_interfaces` service returns detailed WAN configuration
- **Service Response Data**: All services now return response data for automation use
- **UDM Pro Interface Mapping**: Enhanced WAN detection with standard UDM Pro mapping (Internet 1→eth9, Internet 2→eth8)
- **Rate Limiting Protection**: 15-second delays between sequential WAN tests to prevent API rate limiting

### Fixed
- **Dual WAN Speed Testing**: UDM controllers now support testing both WAN interfaces sequentially
- **Scheduler Initialization**: Fixed issue where Python module caching prevented scheduler from initializing (requires full HA restart)
- **Timestamp Display**: Converted Unix milliseconds to human-readable format (e.g., "October 17, 2025 at 1:07:54 PM")
- **Status Field**: Fixed status showing "unknown" instead of "completed" for speed tests
- **Type Hints**: Corrected `unit_of_measurement` type hints to `str | None` for Home Assistant 2025.x compatibility
- **Software Controller Support**: Fixed sensor loading errors for traditional UniFi controllers

### Changed
- **Multi-WAN Testing**: Sequential testing with rate limiting replaces parallel testing to avoid 403 errors
- **Service Schema**: Updated service definitions with proper response support
- **Debug Logging**: Added detailed scheduler initialization logging for troubleshooting

### Technical Notes
- Home Assistant integration "reload" doesn't clear Python module cache - full Docker restart required for code updates
- Scheduler activates on integration load, first test runs after configured interval (default 90 minutes)
- Automated counter only increments when scheduler runs tests, not on reload/restart

## [2.1.1] - 2025-09-12

### Fixed
- **UDM Pro 404 Errors**: Fixed HTTPError 404 issues on UDM Pro devices that don't support advanced routing endpoints
- **Graceful Endpoint Fallback**: Integration now automatically detects when UDM routing endpoints are unsupported and switches to controller mode
- **Reduced Error Logging**: Eliminated repetitive 404 error messages during integration setup
- **Exception Handling**: Improved error handling in routing endpoint detection to prevent setup failures

### Changed
- **Cleaner Setup Process**: UDM routing endpoint testing now handles 404 responses gracefully without logging errors
- **Better Compatibility**: Enhanced support for UDM Pro devices with different firmware versions that may not support all endpoints

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
