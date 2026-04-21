"""One-time Zotify/Spotify login helper.

Fixes the callback server issue where zotify's built-in OAuth flow
dies before the browser can redirect back.

Run once:  python zotify_login.py
After login, zotify will use the saved credentials automatically.
"""
import sys
sys.dont_write_bytecode = True

import os
import json
import webbrowser
import base64
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from pathlib import Path

# Add venv to path
venv_site = Path(__file__).parent / "venv" / "Lib" / "site-packages"
if venv_site.exists():
    sys.path.insert(0, str(venv_site))

from librespot.core import Session
from librespot.mercury import MercuryRequests
from librespot.oauth import OAuth


# Where zotify expects credentials
CREDS_DIR = Path(os.environ.get("APPDATA", "")) / "Zotify"
CREDS_FILE = CREDS_DIR / "credentials.json"


class ReliableCallbackHandler(BaseHTTPRequestHandler):
    """Callback handler that stays alive until we get the actual auth code."""
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/login":
            params = parse_qs(parsed.query)
            if "code" in params:
                self.server.auth_code = params["code"][0]
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b"""<html><body style="background:#1DB954;color:white;
                font-family:sans-serif;display:flex;align-items:center;justify-content:center;
                height:100vh;margin:0"><div style="text-align:center">
                <h1>Login successful!</h1>
                <p>You can close this tab. Go back to the terminal.</p>
                </div></body></html>""")
                return
        # For any other request (favicon, preflight, etc.) — just OK it
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, format, *args):
        pass


def main():
    if CREDS_FILE.exists():
        print(f"Credentials already exist at: {CREDS_FILE}")
        resp = input("Re-login? (y/n): ").strip().lower()
        if resp != "y":
            print("Keeping existing credentials.")
            return

    client_id = MercuryRequests.keymaster_client_id
    redirect_uri = "http://127.0.0.1:4381/login"

    # Create OAuth object and get the auth URL (this generates the PKCE verifier)
    oauth = OAuth(client_id, redirect_uri, lambda url: None)
    auth_url = oauth.get_auth_url()

    # Start our reliable callback server BEFORE opening the browser
    server = HTTPServer(("127.0.0.1", 4381), ReliableCallbackHandler)
    server.auth_code = None
    server.timeout = 300  # 5 minute timeout

    print("\n=== Spotify Login ===")
    print("Opening browser to Spotify login page...")
    print(f"\nIf it doesn't open, visit:\n{auth_url}\n")
    webbrowser.open(auth_url)

    print("Waiting for you to log in...")
    # Keep handling requests until we get the auth code
    while server.auth_code is None:
        server.handle_request()

    server.server_close()
    print("Got authorization code!")

    # Feed the code back to the OAuth object and exchange for token
    oauth.set_code(server.auth_code)
    oauth.request_token()
    login_credentials = oauth.get_credentials()

    print("Token received. Creating Spotify session...")

    # Create a session with store_credentials enabled — this saves in librespot format
    CREDS_DIR.mkdir(parents=True, exist_ok=True)
    builder = Session.Builder()
    builder.conf.store_credentials = True
    builder.conf.stored_credentials_file = str(CREDS_FILE)
    builder.login_credentials = login_credentials
    session = builder.create()

    print(f"\nCredentials saved to: {CREDS_FILE}")
    print("Zotify is now authenticated!")
    print("\nYou can close this window.")


if __name__ == "__main__":
    main()
