# Contributing

Thank you for contributing to the HA UniFi Speedtest Home Assistant custom
integration.

## Supported Scope

Version 4 supports UniFi OS hardware consoles and self-hosted UniFi OS Server
using local API-key authentication. Legacy standalone Network Application
controllers and username/password authentication are outside the supported
scope.

## Development

1. Fork and clone the repository.
2. Create a branch for one focused change.
3. Add or update tests for changed API behavior.
4. Run the local checks:

   ```bash
   python3 -m compileall -q custom_components/ha_unifi_speedtest tests
   python3 -m unittest discover -s tests -v
   git diff --check
   ```

5. Test controller-facing changes against UniFi OS before requesting review.

Never commit API keys, session cookies, controller addresses, public IPs, MAC
addresses, or unsanitized API responses. Fixtures must contain synthetic or
redacted data.

## Pull Requests

Describe the behavior changed, link related issues, and list the checks and
UniFi OS targets used for testing. Update README or changelog content when user
behavior changes.

Contributions must follow the [Code of Conduct](CODE_OF_CONDUCT.md).
