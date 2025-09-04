# Changelog

All notable changes to this project will be documented in this file.

## [2.1.0] - 2025-09-04

### Added
- **Intelligent Primary WAN Detection**: Enhanced logic to properly identify the primary WAN interface based on routing configuration rather than just physical port order
- **Multiple Detection Methods**: 
  - Routing table analysis (checks default route 0.0.0.0/0)
  - Network configuration inspection (looks for explicit primary WAN settings)
  - Speed test data analysis (uses interface with most recent data)
  - Fallback to legacy behavior if advanced detection fails
- **Debug Script**: New `debug_primary_wan.py` script to troubleshoot WAN detection issues
- **Enhanced Logging**: Detailed logging for WAN detection process showing which method was used

### Fixed
- **Primary WAN Misidentification**: Resolves issue where secondary physical ports configured as primary WAN in UniFi showed incorrect `is_primary_wan: false` status
- **Dual WAN Configuration Issues**: Now properly handles configurations where SFP+ ports or other secondary physical ports are configured as the primary WAN

### Changed
- **Primary WAN Logic**: Replaced simple "first interface found" logic with intelligent detection based on actual network configuration
- **Sensor Attributes**: `is_primary_wan` attribute now reflects the actual configured primary WAN, not just port discovery order
- **API Methods**: Enhanced both UDM and traditional controller methods to query routing and configuration endpoints

### Technical Details
- Added new API methods: `_determine_primary_wan_udm()`, `_determine_primary_wan_controller()`
- Added routing info retrieval: `_get_udm_routing_info()`, `_get_controller_routing_info()`
- Added network config analysis: `_get_udm_network_config()`
- Enhanced sensor method: `_determine_is_primary_wan()` with multiple matching strategies
- Improved error handling and fallback mechanisms

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
