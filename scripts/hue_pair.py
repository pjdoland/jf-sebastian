#!/usr/bin/env python3
"""
One-time Philips Hue Bridge pairing for J.F. Sebastian.

Discovers the Bridge on your LAN, prompts you to press the physical link button,
registers this application, caches the API username, and prints an inventory of
every light, room, zone, and scene the Bridge knows about — so you can see
exactly what names José can match against.

Usage:
    python scripts/hue_pair.py                    # discover, pair, list inventory
    python scripts/hue_pair.py --bridge 192.168.1.42  # skip discovery
    python scripts/hue_pair.py --list             # already paired: just list inventory
"""

import argparse
import json
import os
import socket
import stat
import sys
import time
from typing import Optional

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jf_sebastian.config import settings  # noqa: E402

# Honour the configured cache path. Hardcoding it here would strand anyone who
# sets HUE_TOKEN_CACHE: validate() would demand a credential at their path while
# this script wrote to a different one, unfixably.
CACHE_PATH = os.path.expanduser(settings.HUE_TOKEN_CACHE)
DISCOVERY_URL = "https://discovery.meethue.com"
REGISTRATION_TIMEOUT_SECONDS = 90
REGISTRATION_POLL_INTERVAL_SECONDS = 2


def discover_bridge_ip() -> Optional[str]:
    """Ask the Signify discovery service for a Bridge on this LAN."""
    try:
        resp = requests.get(DISCOVERY_URL, timeout=5)
        resp.raise_for_status()
        bridges = resp.json()
    except (requests.RequestException, ValueError) as exc:
        print(f"  discovery service unreachable: {exc}")
        return None
    if not bridges:
        print("  discovery service returned no bridges on this network")
        return None
    if len(bridges) > 1:
        print(f"  discovery returned {len(bridges)} bridges — picking the first")
        for b in bridges:
            print(f"    {b.get('internalipaddress')}  id={b.get('id')}")
    return bridges[0].get("internalipaddress")


def register(bridge_ip: str) -> dict:
    """Poll the Bridge until the user presses the link button, then return the credential dict."""
    device_type = f"jf_sebastian#{socket.gethostname()[:19]}"
    url = f"http://{bridge_ip}/api"
    body = {"devicetype": device_type, "generateclientkey": True}

    print(f"\nPress the physical link button on the Hue Bridge now.")
    print(f"Waiting up to {REGISTRATION_TIMEOUT_SECONDS}s...")

    deadline = time.monotonic() + REGISTRATION_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        try:
            resp = requests.post(url, json=body, timeout=5)
            resp.raise_for_status()
            payload = resp.json()
        except (requests.RequestException, ValueError) as exc:
            print(f"  bridge unreachable: {exc}")
            time.sleep(REGISTRATION_POLL_INTERVAL_SECONDS)
            continue

        if isinstance(payload, list) and payload:
            entry = payload[0]
            if "success" in entry:
                success = entry["success"]
                return {
                    "bridge_ip": bridge_ip,
                    "username": success["username"],
                    "clientkey": success.get("clientkey"),
                }
            if "error" in entry:
                err = entry["error"]
                if err.get("type") == 101:  # link button not pressed
                    time.sleep(REGISTRATION_POLL_INTERVAL_SECONDS)
                    continue
                raise RuntimeError(f"bridge rejected registration: {err.get('description')}")
        time.sleep(REGISTRATION_POLL_INTERVAL_SECONDS)

    raise TimeoutError("timed out waiting for link button press")


def save_credentials(creds: dict) -> None:
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, "w") as f:
        json.dump(creds, f, indent=2)
    try:
        os.chmod(CACHE_PATH, stat.S_IRUSR | stat.S_IWUSR)  # 0600
    except OSError:
        pass
    print(f"\nCredentials cached at {CACHE_PATH} (chmod 0600).")


def load_credentials() -> dict:
    with open(CACHE_PATH) as f:
        return json.load(f)


def _bridge_ip(creds: dict) -> Optional[str]:
    """HUE_BRIDGE_HOST overrides the paired-at address, matching HueTool."""
    return (settings.HUE_BRIDGE_HOST or "").strip() or creds.get("bridge_ip")


def _get(bridge_ip: str, username: str, path: str) -> dict:
    url = f"http://{bridge_ip}/api/{username}/{path}"
    resp = requests.get(url, timeout=5)
    resp.raise_for_status()
    return resp.json()


def print_inventory(bridge_ip: str, username: str) -> None:
    lights = _get(bridge_ip, username, "lights")
    groups = _get(bridge_ip, username, "groups")
    scenes = _get(bridge_ip, username, "scenes")

    print(f"\n=== Lights ({len(lights)}) ===")
    for lid, info in sorted(lights.items(), key=lambda kv: int(kv[0])):
        name = info.get("name", "?")
        model = info.get("modelid", "?")
        state = info.get("state", {})
        on = "on" if state.get("on") else "off"
        reachable = "" if state.get("reachable") else "  [unreachable]"
        print(f"  {lid:>3}  {name!r:<32} {model:<10}  {on}{reachable}")

    rooms = [(gid, g) for gid, g in groups.items() if g.get("type") == "Room"]
    zones = [(gid, g) for gid, g in groups.items() if g.get("type") == "Zone"]
    other = [(gid, g) for gid, g in groups.items() if g.get("type") not in ("Room", "Zone")]

    print(f"\n=== Rooms ({len(rooms)}) ===")
    for gid, g in sorted(rooms, key=lambda kv: int(kv[0])):
        member_count = len(g.get("lights", []))
        print(f"  {gid:>3}  {g.get('name', '?')!r:<32} {g.get('class', ''):<12}  {member_count} light(s)")

    if zones:
        print(f"\n=== Zones ({len(zones)}) ===")
        for gid, g in sorted(zones, key=lambda kv: int(kv[0])):
            member_count = len(g.get("lights", []))
            print(f"  {gid:>3}  {g.get('name', '?')!r:<32}  {member_count} light(s)")

    if other:
        print(f"\n=== Other groups ({len(other)}) ===")
        for gid, g in sorted(other, key=lambda kv: int(kv[0])):
            print(f"  {gid:>3}  {g.get('name', '?')!r:<32}  type={g.get('type')}")

    # Scenes: dedupe by (name, group) — the API returns one entry per stored state
    scene_names = sorted({s.get("name", "?") for s in scenes.values()})
    print(f"\n=== Scenes ({len(scene_names)} unique names, {len(scenes)} total entries) ===")
    for name in scene_names:
        print(f"  {name!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--bridge", metavar="IP", help="skip discovery, use this Bridge IP")
    parser.add_argument("--list", action="store_true", help="already paired; just print inventory")
    args = parser.parse_args()

    if args.list:
        if not os.path.exists(CACHE_PATH):
            print(f"error: no credentials at {CACHE_PATH}. Run without --list to pair first.")
            return 1
        creds = load_credentials()
        host = _bridge_ip(creds)
        if not host:
            print(f"error: {CACHE_PATH} has no bridge address and HUE_BRIDGE_HOST is unset.")
            return 1
        print(f"Using cached credentials for bridge {host}.")
        print_inventory(host, creds["username"])
        return 0

    if args.bridge:
        bridge_ip = args.bridge
        print(f"Using explicit bridge IP: {bridge_ip}")
    else:
        print("Discovering Hue Bridge via discovery.meethue.com...")
        bridge_ip = discover_bridge_ip()
        if not bridge_ip:
            print("\nNo bridge auto-discovered. Find its IP in the Hue app")
            print("(Settings > My Hue System > tap the Bridge) and re-run:")
            print("    python scripts/hue_pair.py --bridge <IP>")
            return 1
        print(f"Found bridge at {bridge_ip}")

    try:
        creds = register(bridge_ip)
    except (TimeoutError, RuntimeError) as exc:
        print(f"\nPairing failed: {exc}")
        return 1

    save_credentials(creds)
    print_inventory(creds["bridge_ip"], creds["username"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
