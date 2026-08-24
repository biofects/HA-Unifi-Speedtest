"""Registry identifier helpers for HA UniFi Speedtest."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .const import DOMAIN

LEGACY_MAIN_DEVICE_ID = "unifi_speedtest"
_SENSOR_METRICS = {"download", "upload", "ping"}


def main_device_identifier(entry_id: str) -> str:
    """Return the config-entry-scoped main device identifier."""
    return f"{LEGACY_MAIN_DEVICE_ID}_{entry_id}"


def wan_device_identifier(entry_id: str, interface: str, group: str) -> str:
    """Return the config-entry-scoped WAN device identifier."""
    return f"{LEGACY_MAIN_DEVICE_ID}_{entry_id}_{interface}_{group}"


def legacy_device_identifier_to_scoped(
    identifier: str, entry_id: str
) -> str | None:
    """Convert a pre-v4 device identifier to its scoped equivalent."""
    if identifier == LEGACY_MAIN_DEVICE_ID:
        return main_device_identifier(entry_id)

    legacy_prefix = f"{LEGACY_MAIN_DEVICE_ID}_"
    scoped_prefix = f"{legacy_prefix}{entry_id}"
    if identifier.startswith(legacy_prefix) and not identifier.startswith(
        scoped_prefix
    ):
        return f"{legacy_prefix}{entry_id}_{identifier.removeprefix(legacy_prefix)}"
    return None


def wan_interface_from_sensor_unique_id(unique_id: str) -> str | None:
    """Extract a WAN interface from legacy or scoped sensor unique IDs."""
    prefix = f"{DOMAIN}_"
    if not unique_id.startswith(prefix):
        return None

    parts = unique_id.removeprefix(prefix).split("_")
    if len(parts) < 3 or parts[0] not in _SENSOR_METRICS:
        return None
    return parts[1]


def active_device_identifiers(
    entry_id: str, coordinator_data: Mapping[str, Any] | None
) -> set[tuple[str, str]]:
    """Return device identifiers currently represented by coordinator data."""
    identifiers = {(DOMAIN, main_device_identifier(entry_id))}
    if not coordinator_data:
        return identifiers

    for wan in coordinator_data.get("wan_interfaces", []):
        interface = wan.get("interface_name") or wan.get("interface")
        if not interface:
            continue
        group = str(wan.get("wan_networkgroup") or "WAN")
        identifiers.add((DOMAIN, wan_device_identifier(entry_id, interface, group)))
    return identifiers