# Changelog

All notable changes to this project will be documented in this file.

## [4.1.0] - 2026-08-24

### Fixed

- Migrates pre-v4 device identifiers in place so upgrades preserve device area,
  labels, and user customizations instead of creating replacement devices.
- Reconciles duplicates already created by v4.0.0 by moving their entities to
  the legacy device record before removing the duplicate.
- Detects inactive WAN entities from the unique ID format instead of assuming
  interfaces are named `eth<N>`, adding support for names such as `ppp0` and
  `wan0`.
- Allows stale integration devices that are no longer reported by the
  coordinator to be removed from Home Assistant's device registry.

## [4.0.0] - 2026-08-23

### Breaking changes

- Requires UniFi OS on a hardware console or self-hosted UniFi OS Server.
- Removes legacy standalone UniFi Network Application controller support.
- Removes username/password authentication and requires a local API key.
- Removes the controller-type selection step from initial configuration.
- Existing API-key entries continue to load. Existing username/password-only
  entries must be removed and configured against UniFi OS with an API key.

### Changed

- Uses one UniFi OS API client for all supported installations.
- Removes bare `/api/s/...` endpoint fallbacks; only UniFi OS
  `/proxy/network/...` routes remain.
- Treats an empty gateway interface table as unsupported and returns an empty
  WAN status map without failing entity updates.
- Adds API contract tests for authentication, trigger acknowledgement, endpoint
  fallback behavior, and empty WAN status data.

## [3.0.0] - 2026-02-23

Focus: Simpler, more robust implementation using official UniFi APIs, proper Multi-WAN support, and better UX.

### Breaking changes
- **Authentication switched to API Key or Username/Password**
  - UDM/UniFi OS controllers use API Key authentication (sent via the `X-API-KEY` header)
  - Self-hosted controllers use username/password authentication with session management
  - You must select your controller type during setup (UDM or Self-hosted)
- **Configuration flow updated**
  - Two-step process: First select controller type, then provide credentials
  - UDM: Requires Base URL, API Key, and Site
  - Self-hosted: Requires Base URL, Username, Password, and Site
  - Optional: Verify SSL, Enable Multi-WAN, Show Inactive WANs
- **Sensor naming updated for Multi-WAN**
  - Multi-WAN sensor names are now compact: `Download Speed WAN`, `Upload Speed WAN2`, `Ping WAN`
  - Primary/Secondary role displayed in device name: "HA Unifi Speedtest Primary WAN [WAN - eth9]"
  - If you had pinned entities by name in dashboards/automations, you may need to update them after upgrading
- **First-time entity creation now happens after data is present**
  - Multi-WAN entities are created dynamically once speed test data exists for a WAN, avoiding ghost/placeholder entities
  - Entities for new WANs are added automatically when they become active

### New
- **Separated API architecture**
  - Hardware API (`api_hardware.py`) for UDM/UniFi OS with API key authentication
  - Software API (`api_software.py`) for self-hosted controllers with session authentication
  - Base API class (`api_base.py`) with common functionality
  - Factory pattern (`api_factory.py`) for clean API instantiation
- **Official UniFi API usage throughout**
  - Sites: `GET /proxy/network/integration/v1/sites`
  - WANs (for discovery): `GET /proxy/network/integration/v1/sites/{siteId}/wans`
  - Speedtest history: `GET /proxy/network/v2/api/site/{site}/speedtest`
  - Trigger test (with fallbacks):
    - `POST /proxy/network/api/s/{site}/cmd/devmgr/speedtest`
    - `POST /proxy/network/api/s/{site}/cmd/devmgr` with `{ "cmd": "speedtest" }`
    - `POST /proxy/network/v2/api/site/{site}/speedtest`
- **Proper Multi-WAN sensors**
  - Creates sensors per WAN group (WAN, WAN2, WAN3, …) based on actual speedtest results
  - Each WAN interface gets its own device in Home Assistant
  - Primary/Secondary role detection improved (prefers `WAN`, otherwise most capable/recent)
- **Button platform**
  - "Run Speedtest (All WANs)" button for triggering tests on all interfaces
  - Per-WAN buttons (e.g., `Run Speedtest (WAN2 - eth9)`) created dynamically once that WAN has data
- **Faster UI updates after a test**
  - Follow-up data refreshes scheduled automatically after manual and scheduled test triggers (e.g., ~10/30/60/120s)
  - Results appear quickly without waiting for the next polling interval
- **Option: Show inactive WANs (default: hidden)**
  - By default, WANs with no link or no IP are hidden from sensors
  - New option in config flow allows showing inactive WANs if desired
  - Helps reduce clutter when WANs are temporarily disconnected
- **Clearer device and sensor names**
  - Devices use compact format with both WAN group (`WAN/WAN2/...`) and interface (e.g., `eth9`)
  - Primary/Secondary role shown in device name for easy identification
  - Sensor names simplified: "Download Speed WAN", "Upload Speed WAN2", etc.
- **Integration icon**
  - Added custom icon for Home Assistant integration branding
  - Thanks to @esand for the icon design (issue #35)

### Changes
- **No more login churn**
  - UDM integration reuses a single session with API Key; no CSRF or credential logins
  - Self-hosted integration maintains session with proper cookie management
- **Scheduling improvements**
  - Randomized delay (0-60s) to avoid thundering herd on the controller
  - Automatic post-test refreshes to surface results faster
  - Polling interval automatically derived from schedule interval when enabled
- **Error handling & logging**
  - Better mapping of common errors in config flow (`invalid_auth`, `cannot_connect`, `unknown`)
  - More informative logs for HTTP errors (constructed vs actual request URL, status, snippet of body)
  - Graceful degradation when API endpoints are unavailable
- **Safer entity creation**
  - Multi-WAN sensors/buttons are added only for WANs that report data (and, by default, are active)
  - Avoids duplicates and placeholder entities
  - Dynamic addition of new WANs without requiring integration reload

### Fixed
- **Only "WAN" showing issue**
  - Now discovers and exposes all configured WAN groups (WAN2, WAN3, …) when test data exists
  - Each WAN gets its own device with separate sensors
- **Triggering tests inconsistently (404 or wrong method)**
  - Now always uses `POST` and tries multiple officially supported endpoints to handle firmware differences
  - Fallback logic ensures tests trigger successfully across different UniFi OS versions
- **Over-eager login attempts / session churn**
  - Replaced with API key session reuse for UDM
  - Proper session management for self-hosted controllers
- **Entity device reference warnings**
  - Removed invalid `via_device` references that caused deprecation warnings
  - Each WAN device is now independent

### Migration notes
1. **For UDM users**: Generate an API key on your UDM/UniFi OS:
   - Go to Settings → Admins → [Your Admin] → API Key
   - Copy the generated key
2. **For self-hosted controller users**: Ensure you have admin credentials
3. In Home Assistant:
   - Remove the old configuration entry if upgrading from 2.x
   - Add the integration again:
     - Select controller type (UDM or Self-hosted)
     - Provide credentials (API Key for UDM, Username/Password for Self-hosted)
     - URL: `https://<your-udm-or-controller>`
     - Site: usually `default`
     - Verify SSL: toggle off for self-signed certificates
4. If dashboards reference old entity names, update them to the new compact naming
5. Optional: Enable "Show inactive WANs" in integration options if you want to display unplugged/no-IP WANs

### Notes
- Multi-WAN entities appear after a speedtest result is available per WAN
- Consider running a manual test via the new buttons to seed data quickly after setup
- Per-WAN buttons appear once a WAN has been observed in speedtest data and (by default) is active
- The integration now uses a cleaner, more maintainable codebase with separated concerns

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
