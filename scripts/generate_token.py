#!/usr/bin/env python3
"""
Einmaliges Script: Generiert einen Google OAuth Token.
Öffnet den Browser, du loggst dich ein, und der Token wird gespeichert.
"""
import json
import os
os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/gmail.readonly"
]

CREDENTIALS_FILE = "/Users/emil./Downloads/client_secret_2_1072463896579-jkig8hgpp4rl4is9hbdjbb8nqkavuo5c.apps.googleusercontent.com.json"

def main():
    print("Starte Google Login...")
    print("Dein Browser öffnet sich gleich - bitte einloggen und Zugriff erlauben.")
    print()

    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
    creds = flow.run_local_server(port=8090)

    token_data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes)
    }

    output_file = "/Users/emil./Downloads/google_token.json"
    with open(output_file, "w") as f:
        json.dump(token_data, f, indent=2)

    print()
    print(f"Token gespeichert in: {output_file}")
    print()
    print("=== NÄCHSTE SCHRITTE ===")
    print("Diesen Token und die Credentials musst du als GitHub Secrets speichern.")
    print("Das macht Claude für dich im nächsten Schritt.")

if __name__ == "__main__":
    main()
