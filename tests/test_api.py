"""Contract tests for the UniFi OS speed-test API client."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock


COMPONENT_DIR = (
    Path(__file__).parents[1] / "custom_components" / "ha_unifi_speedtest"
)
PACKAGE_NAME = "ha_unifi_speedtest_under_test"


def _load_module(module_name: str):
    """Load API modules without importing the Home Assistant integration setup."""
    full_name = f"{PACKAGE_NAME}.{module_name}"
    spec = importlib.util.spec_from_file_location(
        full_name,
        COMPONENT_DIR / f"{module_name}.py",
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
api = _load_module("api")


class FakeResponse:
    """Minimal response object used by the API client."""

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class UniFiOSSpeedTestTests(unittest.TestCase):
    """Verify that HTTP success is not mistaken for command success."""

    def setUp(self):
        self.api = api.UniFiOSAPI(
            "https://unifi.example",
            api_key="test-key",
        )
        self.api._site_id = "site-uuid"

    def test_requires_api_key(self):
        with self.assertRaisesRegex(ValueError, "API key is required"):
            api.UniFiOSAPI("https://unifi.example", api_key="")

    def test_sets_api_key_header(self):
        self.assertEqual("test-key", self.api.session.headers["X-API-KEY"])

    def test_connection_uses_site_discovery(self):
        self.api._site_id = None
        self.api._request = Mock(
            return_value=FakeResponse(
                {
                    "data": [
                        {"internalReference": "default", "id": "site-uuid"}
                    ]
                }
            )
        )

        self.assertTrue(self.api.test_connection())
        self.assertEqual(
            "/proxy/network/integration/v1/sites",
            self.api._request.call_args.args[1],
        )

    def test_returns_only_after_unifi_acknowledges_command(self):
        self.api._request = Mock(
            side_effect=[
                FakeResponse({"meta": {"rc": "error"}, "data": []}),
                FakeResponse({"meta": {"rc": "ok"}, "data": []}),
            ]
        )

        result = self.api.start_speed_test("eth4")

        self.assertEqual("ok", result["meta"]["rc"])
        self.assertEqual(2, self.api._request.call_count)
        second_call = self.api._request.call_args_list[1]
        self.assertEqual(
            "/proxy/network/api/s/default/cmd/devmgr",
            second_call.args[1],
        )
        self.assertEqual(
            {"cmd": "speedtest", "interface_name": "eth4"},
            second_call.kwargs["json"],
        )

    def test_raises_when_no_endpoint_acknowledges_command(self):
        self.api._request = Mock(
            side_effect=[
                FakeResponse({"meta": {"rc": "error"}, "data": []}),
                FakeResponse({"result": "ignored"}),
                FakeResponse({"data": []}),
                FakeResponse(None),
            ]
        )

        with self.assertRaisesRegex(RuntimeError, "did not acknowledge"):
            self.api.start_speed_test()

        attempted_paths = [
            call.args[1] for call in self.api._request.call_args_list
        ]
        self.assertEqual(
            [
                "/proxy/network/api/s/default/cmd/devmgr/speedtest",
                "/proxy/network/api/s/default/cmd/devmgr",
                "/proxy/network/s/default/cmd/devmgr",
            ],
            attempted_paths,
        )
        self.assertNotIn(
            "/proxy/network/v2/api/site/default/speedtest",
            attempted_paths,
        )

    def test_empty_device_list_returns_empty_wan_status(self):
        self.api._request = Mock(side_effect=[FakeResponse({"data": []})])

        self.assertEqual({}, self.api.get_wan_status_map())


if __name__ == "__main__":
    unittest.main()