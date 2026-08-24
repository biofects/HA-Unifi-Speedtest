"""Tests for device and entity registry identifier handling."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types
import unittest


COMPONENT_DIR = (
    Path(__file__).parents[1] / "custom_components" / "ha_unifi_speedtest"
)
PACKAGE_NAME = "ha_unifi_speedtest_registry_under_test"


def _load_module(module_name: str):
    full_name = f"{PACKAGE_NAME}.{module_name}"
    spec = importlib.util.spec_from_file_location(
        full_name, COMPONENT_DIR / f"{module_name}.py"
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {module_name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[full_name] = module
    spec.loader.exec_module(module)
    return module


package = types.ModuleType(PACKAGE_NAME)
package.__path__ = [str(COMPONENT_DIR)]
sys.modules.setdefault(PACKAGE_NAME, package)
_load_module("const")
registry = _load_module("registry")


class RegistryIdentifierTests(unittest.TestCase):
    def test_scopes_legacy_main_device(self):
        self.assertEqual(
            "unifi_speedtest_entry123",
            registry.legacy_device_identifier_to_scoped(
                "unifi_speedtest", "entry123"
            ),
        )

    def test_scopes_ppp_wan_device(self):
        self.assertEqual(
            "unifi_speedtest_entry123_ppp0_WAN",
            registry.legacy_device_identifier_to_scoped(
                "unifi_speedtest_ppp0_WAN", "entry123"
            ),
        )

    def test_does_not_rescope_current_device(self):
        self.assertIsNone(
            registry.legacy_device_identifier_to_scoped(
                "unifi_speedtest_entry123_ppp0_WAN", "entry123"
            )
        )

    def test_extracts_non_ethernet_interfaces(self):
        for interface in ("ppp0", "wan0", "eth9"):
            with self.subTest(interface=interface):
                self.assertEqual(
                    interface,
                    registry.wan_interface_from_sensor_unique_id(
                        f"ha_unifi_speedtest_download_{interface}_WAN_entry123"
                    ),
                )

    def test_ignores_non_wan_sensor_ids(self):
        self.assertIsNone(
            registry.wan_interface_from_sensor_unique_id(
                "ha_unifi_speedtest_api_health_entry123"
            )
        )

    def test_active_identifiers_include_reported_ppp_wan(self):
        identifiers = registry.active_device_identifiers(
            "entry123",
            {
                "wan_interfaces": [
                    {"interface_name": "ppp0", "wan_networkgroup": "WAN"}
                ]
            },
        )
        self.assertIn(
            ("ha_unifi_speedtest", "unifi_speedtest_entry123_ppp0_WAN"),
            identifiers,
        )


if __name__ == "__main__":
    unittest.main()