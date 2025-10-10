# Changelog

All notable changes to this project will be documented in this file.

## [2.2.0] - 2025-10-10

### Major Changes
- **Controller Type Selection**: Removed automatic controller detection in favor of user-controlled selection
- **UDM Multi-WAN Logic**: UDM controllers now intelligently detect multiple WAN connections and create entities accordingly
- **Traditional Controller Support**: Self-hosted controllers now use single-WAN mode with appropriate endpoints

### Added
- **Smart Entity Creation**: Only creates entities for actually connected WAN interfaces
- **Improved UI**: Enhanced configuration flow with clear controller type descriptions
- **Connection-Based Detection**: For UDMs, detects which WANs are connected and only creates entities for active connections
- **Clean Naming**: Single WAN connections get clean names without WAN number suffixes

### Fixed
- **Authentication Issues**: Resolved 401/404 errors caused by incorrect controller type detection
- **Endpoint Selection**: Fixed issues where UDM endpoints were being used for self-hosted controllers and vice versa
- **Entity Creation**: Eliminated creation of "Unknown" entities that couldn't be removed
- **Multi-WAN Detection**: Improved detection of dual-WAN setups on UDM devices

### Changed
- **Configuration Options**: Controller type selection now shows "UDM Pro/SE/Cloud Key Gen2+" vs "Self-hosted Controller"
- **API Logic**: Simplified API calls to use user-specified controller type without auto-detection
- **Sensor Logic**: UDM controllers check for multiple WANs, traditional controllers use single WAN mode
- **Error Handling**: Better error messages and fallback behavior when no speedtest data is available

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
