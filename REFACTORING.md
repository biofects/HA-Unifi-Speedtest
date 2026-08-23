# Refactoring and Test Strategy

## Goals

The next stable release should make controller behavior explicit, keep blocking
I/O out of Home Assistant's event loop, and make failures observable instead of
returning stale data or false success.

## Proposed Architecture

1. **API clients** own authentication, HTTP transport, endpoint capabilities,
   response validation, and normalized speed-test records.
2. **Coordinator** owns all periodic reads, discovered WANs, availability, and
   the latest normalized data. It is created before platforms are forwarded.
3. **Speed-test manager** owns trigger serialization, scheduling, completion
   polling, and run history. Buttons and services call this manager.
4. **Entities** only render coordinator state. They do not discover WANs, make
   API calls, schedule work, or mutate the entity registry.
5. **Config flow** validates credentials and creates entries. It does not infer
   controller type from whichever credentials happen to be present.

Store one runtime object per config entry instead of placing API clients,
trackers, coordinators, listeners, and WAN maps under related string keys in
`hass.data`.

## Delivery Order

### Phase 1: API Contracts

- Record sanitized UDM Pro responses for site discovery, WAN discovery, status,
  trigger success, permission failure, and unsupported endpoints.
- Require a UniFi command acknowledgement before reporting trigger success.
- Normalize controller responses into typed records.
- Distinguish authentication, permission, unsupported, timeout, and transport
  errors. Do not turn every failure into cached success.

This phase addresses issues #43 and #47 and creates a stable boundary for the
Home Assistant code.

### Phase 2: Home Assistant Runtime

- Create the coordinator in integration setup before forwarding platforms.
- Use `ConfigEntry.runtime_data` for the entry-scoped runtime object.
- Forward sensor and button platforms together after runtime initialization.
- Register coordinator listeners with config-entry unload callbacks.
- Replace delayed refresh loops with one bounded completion-polling task.
- Register domain services once and remove them when the last entry unloads.

This phase addresses issues #42, #45, and #48.

### Phase 3: Entities and Migration

- Use entity descriptions for download, upload, ping, health, and run data.
- Give every entity and device an entry-scoped stable identifier.
- Add a config-entry migration for existing unique IDs.
- Never delete entity-registry entries during platform setup.
- Define whether run counts mean tests requested by Home Assistant, tests
  observed on the controller, or both, and expose those as separate values.

This phase addresses issue #44 and prevents duplicate or zombie entities.

### Phase 4: Release Hardening

- Add config-flow, setup/unload, coordinator, service, and entity tests using
  Home Assistant's pytest fixtures.
- Add diagnostics with credentials, host details, and API keys redacted.
- Replace broad exception handling and f-string logging in touched code.
- Run unit tests, hassfest, and HACS validation on every pull request.

## Test Matrix

| Target | What it proves | Required for pull requests |
| --- | --- | --- |
| Mocked HTTP responses | Endpoint order, payloads, parsing, errors | Yes |
| Home Assistant test harness | Lifecycle, services, entities, migrations | Yes |
| Self-hosted UniFi OS Server | API-key auth and UniFi OS proxy APIs | Nightly/manual |
| UDM Pro staging site | UniFi OS API key, WANs, real trigger and results | Release candidate |

### Container Scope

A self-hosted UniFi OS Server is useful for validating the same API-key and
`/proxy/network` path used by hardware consoles, but it is not a UDM Pro
emulator. A server without an adopted gateway cannot validate physical WAN
interfaces or a gateway speed test.

Keep the UniFi OS Server stack optional because first-run setup and gateway
adoption make it unsuitable as the fast pull-request test. Legacy standalone
Network Application containers are explicitly outside the v4 support matrix.

For UDM Pro release checks, use a dedicated local API key with the least
privilege that supports the tested operations. Never capture cookies, API keys,
public IPs, MAC addresses, or controller hostnames in fixtures.