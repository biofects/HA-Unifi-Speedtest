# Spec: Drop Legacy Software-Controller Support in HA-Unifi-Speedtest

**Based on:** `biofects/HA-Unifi-Speedtest` @ `v3.1.4rc5`
**Goal:** Require UniFi OS (hardware console *or* self-hosted UniFi OS Server) for every install. Remove the separate "self-hosted software controller" (username/password, unprefixed `/api/...`) code path entirely.

---

## 1. Why this is doable

The repo already cleanly separates the two controller types into two classes behind a factory:

- `api_hardware.py` → `UniFiHardwareAPI` — API-key auth, `/proxy/network/...` paths (UniFi OS).
- `api_software.py` → `UniFiSoftwareAPI` — username/password session auth, bare `/api/...` paths (legacy standalone).
- `api_factory.py` → `create_unifi_api()` picks one based on `controller_type` (`"udm"` vs `"controller"`).
- `api_base.py` → shared HTTP/session/retry logic both subclass.

Since you're now running your second test target as a UniFi OS Server (not legacy standalone), both of your dev environments will only ever need `UniFiHardwareAPI`. `UniFiSoftwareAPI` becomes dead code, and `api_factory.py`'s branching becomes unnecessary.

---

## 2. Files to change

### 2.1 Delete
- `custom_components/ha_unifi_speedtest/api_software.py` — entire file, no longer used.

### 2.2 Collapse `api_factory.py`
- Remove `controller_type` branching. `create_unifi_api()` should always return `UniFiHardwareAPI`.
- Remove the `username`/`password` parameters (or keep them accepted-but-ignored for one release if you want a soft deprecation — see §5).
- Keep `api_key` as the only required credential.
- Update/remove the legacy `UniFiAPI()` back-compat wrapper, or have it hard-fail with a clear `ValueError` pointing users at the new API-key-only flow.

### 2.3 Rename/simplify `api_hardware.py`
- Optional but recommended: rename `UniFiHardwareAPI` → `UniFiOSAPI` (or just leave the name; "hardware" is a bit inaccurate once a Docker UniFi OS Server is a valid target, but renaming is cosmetic — do it only if you're comfortable with the diff noise in `__init__.py`/`sensor.py`/tests).
- No endpoint-fallback logic needs to change here — the `/proxy/network/...` attempts already work for both console and UniFi OS Server since they speak the same API.
- **Trim the endpoint fallback lists.** Right now `start_speed_test()`, `get_wan_interfaces()`, `get_speed_test_status()`, and `get_wan_status_map()` each try 3–5 endpoint variants (including bare `/api/s/...` paths without the `/proxy/network` prefix — those were there to cover *both* Cloud Gateway quirks and legacy fallbacks). Once legacy is out of scope:
  - Keep the `/proxy/network/...`-prefixed variants (these cover real UniFi OS version differences you'll still hit across console vs Docker UniFi OS Server).
  - Drop the bare `/api/s/...` (no `/proxy/network` prefix) fallback entries specifically — those exist only for non-UniFi-OS installs.
  - This shortens each retry loop by one entry and removes ambiguity about *why* a given attempt exists.

### 2.4 `api_base.py`
- No changes needed structurally. `controller_type` field can be removed from the constructor signature (always `"udm"`), or left as a vestigial default — your call on how much you want to simplify vs. minimize diff size.

### 2.5 `config_flow.py`
- Remove the first wizard step that asks the user to choose `controller_type` (`vol.In({...})` around line 71).
- Collapse straight to the credentials step, always requesting:
  - `url`
  - `api_key` (with the existing helper text: "Generate one in Settings → Admins → [Your Admin] → API Key.")
  - `site`
  - `verify_ssl`
- Remove the `username`/`password` fields and the `if self.controller_type == 'controller':` branch (~line 107).
- Update error handling around line 151–156 — the "username and password required" branch goes away; only the "API key required" message remains.
- Update the options flow (`current_controller_type` handling around line 254/284) the same way.

### 2.6 `const.py`
- Remove `CONF_USERNAME`, `CONF_PASSWORD` if nothing else uses them (double check `strings.json`/`translations/en.json` for form field labels referencing these — update those too).
- `CONF_CONTROLLER_TYPE` can be removed or kept-but-unused for backward config-entry compatibility (see §5).

### 2.7 `__init__.py`
- Remove the `controller_type` detection/branch logic (lines ~37–77): no more "detect from username/password presence" fallback, no more `if controller_type == "udm" / elif == "controller"` split.
- Always call `create_unifi_api(url=..., api_key=..., site=..., verify_ssl=...)`.
- Simplify the log line at ~77 to drop `controller_type` from the message (or hardcode `"unifi_os"`).

### 2.8 `sensor.py`
- Remove/simplify the three spots keyed on `api.controller_type == 'udm'` (lines ~65, ~294) — that condition becomes always-true, so either delete the branch or leave a single unconditional path.
- Line ~931/972 (`self._controller_type` stored/exposed as a sensor attribute) — decide whether to keep exposing this as `"unifi_os"` for informational value or drop it.

### 2.9 `manifest.json` / `hacs.json` / `README.md`
- Update requirements text to state plainly: **"Requires UniFi OS — a UDM/UDM Pro/UDM-SE/Cloud Gateway/Cloud Key Gen2+, or a self-hosted UniFi OS Server. Legacy standalone Network Application controllers (username/password auth) are not supported."**
- Update any setup screenshots/instructions (`images/configwan.png`, `images/wan1.png`, `images/wan2.png`) if they show the removed controller-type-picker step.
- Bump version appropriately (see §5 on whether this is a major/breaking bump).

---

## 3. Testing checklist

Run this against **both** of your dev targets to confirm true parity now that there's one code path:

- [ ] Config flow completes with API key only (no controller-type prompt appears) — test against UDM Pro.
- [ ] Config flow completes identically — test against Docker UniFi OS Server.
- [ ] `start_speed_test()` succeeds on both targets (confirms the trimmed fallback list still covers real version differences).
- [ ] `get_wan_interfaces()` returns expected WAN(s) on both. Multi-WAN on UDM Pro if you have it configured; single WAN expected on the Docker instance unless you've configured more.
- [ ] `get_speed_test_status()` parses correctly on both after a manual speed test.
- [ ] `get_wan_status_map()` — expect this to return real interface data on UDM Pro (physical NICs); on the Docker UniFi OS Server this may come back empty/partial since there's no real hardware interface table. **Decide now**: should the integration treat an empty status map as "unsupported, skip gracefully" rather than an error? (It already returns `{}` gracefully per the existing code — just confirm no downstream code assumes a non-empty dict.)
- [ ] Old config entries created under the previous version (with `controller_type: "controller"` stored) don't crash `__init__.py` on load — see migration note below.
- [ ] `test_connection()` passes on both.

---

## 4. Edge case to design for explicitly

`get_wan_status_map()` in `UniFiHardwareAPI` walks the device list looking for a gateway device (`udm`, `udmpro`, `usg`, etc.) with an `if_table`/`ifTable`. A Docker UniFi OS Server instance may not report itself as one of those device types, or may report an empty/synthetic interface table since there's no real WAN hardware behind it. Right now the code already degrades gracefully to `{}` — just add a test case confirming the sensor layer doesn't choke on that (e.g. WAN "up/down" sensors should show unavailable/unknown rather than throwing).

---

## 5. Migration / versioning decision (you need to pick one)

Existing users of the current release who are on legitimate *legacy standalone* controllers will break entirely once this ships — that's the intended outcome per your decision, but it affects how you version and communicate it:

- **Option A — Clean break, major version bump.** Update `CHANGELOG.md` and the release notes with a clear "BREAKING: legacy standalone Network Application controllers are no longer supported; migrate to UniFi OS Server or a UniFi OS console" notice. Simplest code, clearest message.
- **Option B — Soft landing.** Keep `config_flow.py` able to *read* an old config entry with `controller_type: "controller"` and show a repair/reauth flow directing the user to switch to UniFi OS, rather than a silent crash on next HA restart. More user-friendly, more code to maintain temporarily.

Given you've already decided "I do not support the legacy," **Option A** is consistent with that and is the smaller, cleaner change — recommend going that route and just being loud about it in the release notes/README.

---

## 6. Rough order of operations

1. Delete `api_software.py`, update `api_factory.py` to be hardware/UniFi-OS-only.
2. Update `__init__.py` to drop branching.
3. Update `config_flow.py` to drop the controller-type step and username/password fields.
4. Update `sensor.py` conditionals.
5. Trim fallback endpoint lists in `api_hardware.py`.
6. Update `const.py`, `strings.json`, `translations/en.json`.
7. Update `README.md`, `manifest.json`/`hacs.json` version + requirements text, screenshots if needed.
8. Test against both your UDM Pro and Docker UniFi OS Server per §3.
9. Update `CHANGELOG.md` with the breaking-change notice, bump major version, release.