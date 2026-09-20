#!/usr/bin/env python
"""
Diagnostic utility: Test SMTP connection and Gmail App Password configuration.

Usage:
    python backend/scripts/test_smtp_connection.py
"""

import sys
import os

# Ensure backend can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from backend.app.config import settings
from backend.app.core.email import test_smtp_connection


def main():
    print("=" * 64)
    print(" SocialProof — SMTP Configuration Diagnostic Tool")
    print("=" * 64)
    print(f"SMTP Host:       {settings.SMTP_HOST}")
    print(f"SMTP Port:       {settings.SMTP_PORT}")
    print(f"SMTP From Name:  {settings.SMTP_FROM_NAME}")
    print(f"SMTP From Email: {settings.SMTP_FROM_EMAIL or '(defaults to username)'}")

    masked_user = (
        f"{settings.SMTP_USERNAME[:3]}...{settings.SMTP_USERNAME[-10:]}"
        if len(settings.SMTP_USERNAME) > 13
        else ("(set)" if settings.SMTP_USERNAME else "(NOT SET)")
    )
    has_pwd = "(SET - " + str(len(settings.SMTP_PASSWORD)) + " chars)" if settings.SMTP_PASSWORD else "(NOT SET)"
    print(f"SMTP Username:   {masked_user}")
    print(f"SMTP Password:   {has_pwd}")
    print("-" * 64)

    if not settings.is_smtp_configured:
        print("[ERROR] SMTP is NOT fully configured in .env!")
        print()
        print("To configure Gmail SMTP:")
        print("1. Open your .env file at project root (f:\\Com Bot Project\\.env)")
        print("2. Set SMTP_USERNAME to your full Gmail address (e.g. yourname@gmail.com)")
        print("3. Set SMTP_PASSWORD to your 16-character Google App Password")
        print("   (Note: Use a Google App Password, NOT your regular account password!)")
        print("4. How to generate a Gmail App Password:")
        print("   a. Visit https://myaccount.google.com/security")
        print("   b. Enable 2-Step Verification if not already enabled")
        print("   c. Search for 'App Passwords' or go to https://myaccount.google.com/apppasswords")
        print("   d. App name: 'SocialProof' -> Generate")
        print("   e. Copy the 16-letter password into SMTP_PASSWORD in .env")
        print("=" * 64)
        sys.exit(1)

    print("Testing connection and authentication with SMTP server...")
    ok, message = test_smtp_connection()
    if ok:
        print(f"[SUCCESS] {message}")
        print("Real email delivery is ready to send verification and password reset emails!")
        print("=" * 64)
        sys.exit(0)
    else:
        print(f"[FAILURE] {message}")
        print()
        print("Troubleshooting steps:")
        print("- Verify that 2-Step Verification is active on your Google account.")
        print("- Verify that SMTP_PASSWORD is a generated 16-character App Password.")
        print("- Ensure there are no typos in SMTP_USERNAME or SMTP_PASSWORD.")
        print("=" * 64)
        sys.exit(1)


if __name__ == "__main__":
    main()
