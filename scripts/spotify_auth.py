#!/usr/bin/env python3
"""
One-time Spotify authorization for J.F. Sebastian (PKCE, no client secret).

Run this ONCE on a machine that has a web browser (e.g. your Mac). It opens a
Spotify login, caches a refresh token, and then lists your available Spotify
Connect devices so you know exactly what to put in SPOTIFY_DEFAULT_DEVICE /
SPOTIFY_DEVICE_ALIASES.

For a headless box (e.g. a Jetson): run this on a browser machine, then copy the
cached token file (SPOTIFY_TOKEN_CACHE, default ~/.config/jf-sebastian/
spotify-token.json) to the same path on the device. See docs/SPOTIFY_SETUP.md.

Usage:
    python scripts/spotify_auth.py            # authorize + list devices
    python scripts/spotify_auth.py --devices  # just list devices (already authorized)
"""

import os
import stat
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jf_sebastian.config import settings  # noqa: E402
from jf_sebastian.modules.spotify_tool import build_spotify_client  # noqa: E402


def main() -> int:
    client_id = (settings.SPOTIFY_CLIENT_ID or "").strip()
    if not client_id:
        print("error: SPOTIFY_CLIENT_ID is not set. Create a Spotify app at")
        print("       https://developer.spotify.com/dashboard, add the redirect URI")
        print(f"       {settings.SPOTIFY_REDIRECT_URI!r}, and set SPOTIFY_CLIENT_ID in .env.")
        return 1

    cache_path = os.path.expanduser(settings.SPOTIFY_TOKEN_CACHE)
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)

    devices_only = "--devices" in sys.argv[1:]
    try:
        # Same auth construction the runtime uses, just with the browser enabled.
        sp = build_spotify_client(cache_path, open_browser=not devices_only, requests_timeout=10)
    except ImportError:
        print("error: spotipy not installed. Run: pip install -r requirements-spotify.txt")
        return 1

    # Force the token exchange (prompts login on first run), then lock the cache 0600.
    me = sp.current_user()
    try:
        os.chmod(cache_path, stat.S_IRUSR | stat.S_IWUSR)  # 0600: a refresh token is a credential
    except OSError:
        pass
    print(f"Authorized as {me.get('display_name') or me.get('id')}.")
    print(f"Token cached at {cache_path} (chmod 0600).")

    print("\nAvailable Spotify Connect devices (use these exact names):")
    devices = sp.devices().get("devices", [])
    if not devices:
        print("  (none active right now; wake a speaker / open the Spotify app and re-run --devices)")
    for d in devices:
        active = " [active]" if d.get("is_active") else ""
        print(f"  - {d['name']}  ({d['type']}){active}")
    print("\nSet SPOTIFY_DEFAULT_DEVICE to one of the names above (and optional")
    print("SPOTIFY_DEVICE_ALIASES like 'kitchen=Kitchen Echo,den=Living Room').")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
