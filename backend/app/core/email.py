"""
Email service using Python stdlib smtplib — no extra dependencies required.

Sends HTML verification and password-reset emails via Gmail SMTP (TLS on port 587).

Configuration (all in .env):
    SMTP_HOST=smtp.gmail.com
    SMTP_PORT=587
    SMTP_USERNAME=you@gmail.com
    SMTP_PASSWORD=xxxx xxxx xxxx xxxx   # Gmail App Password
    SMTP_FROM_EMAIL=you@gmail.com       # Optional — defaults to SMTP_USERNAME
    SMTP_FROM_NAME=SocialProof
    APP_BASE_URL=http://127.0.0.1:8000
"""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Tuple

from backend.app.config import settings

logger = logging.getLogger(__name__)


# ─── Shared helpers ──────────────────────────────────────────────────────────

def _from_address() -> str:
    email = settings.SMTP_FROM_EMAIL or settings.SMTP_USERNAME
    name = settings.SMTP_FROM_NAME or "SocialProof"
    return f"{name} <{email}>" if email else name


def _send(to_email: str, subject: str, html_body: str, text_body: str) -> Tuple[bool, str | None]:
    """
    Core SMTP sender.
    Returns (True, None) on success or (False, error_message) on failure.

    When SMTP is not configured, falls back to printing the full email content
    (including verification/reset links) to the server terminal so developers
    can test the complete email verification flow without real SMTP credentials.
    """
    if not settings.is_smtp_configured:
        # ── Dev Console Fallback ──────────────────────────────────────────────
        # Print the full email to the server terminal so you can copy the
        # verification / reset link directly from the uvicorn logs and open it
        # in your browser to complete the flow end-to-end.
        separator = "=" * 72
        print(f"\n{separator}")
        print(f"[DEV EMAIL] To      : {to_email}")
        print(f"[DEV EMAIL] Subject : {subject}")
        print(f"{'-' * 72}")
        print(text_body.strip().encode("ascii", "replace").decode("ascii"))
        print(f"{separator}\n", flush=True)
        logger.info("[DEV EMAIL] Email printed to console for: %s", to_email)
        return True, None

    try:
        message = MIMEMultipart("alternative")
        message["Subject"] = subject
        message["From"] = _from_address()
        message["To"] = to_email

        message.attach(MIMEText(text_body, "plain", "utf-8"))
        message.attach(MIMEText(html_body, "html", "utf-8"))

        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            server.sendmail(settings.SMTP_USERNAME, to_email, message.as_string())

        logger.info(f"Email '{subject}' successfully sent to {to_email}")
        return True, None

    except smtplib.SMTPAuthenticationError as exc:
        logger.error(f"SMTP authentication failed: {exc}")
        return False, "Unable to send verification email. Please try again later."

    except smtplib.SMTPRecipientsRefused as exc:
        logger.error(f"Recipient refused by SMTP server for {to_email}: {exc}")
        return False, f"The address {to_email} was rejected by the mail server. Please check that the address is correct."

    except smtplib.SMTPException as exc:
        logger.error(f"SMTP sending exception: {exc}")
        return False, "Unable to send verification email. Please try again later."

    except OSError as exc:
        logger.error(f"Network error while connecting to SMTP server: {exc}")
        return False, "Unable to send verification email. Please try again later."


def test_smtp_connection() -> Tuple[bool, str]:
    """
    Diagnostic tool to verify SMTP server connectivity and credentials.
    Does NOT send an email. Connects, issues STARTTLS, and tests authentication.
    Returns (True, "Connection and authentication successful") or (False, reason).
    Credentials are never exposed in return strings.
    """
    if not settings.is_smtp_configured:
        return False, "SMTP is not configured: SMTP_USERNAME or SMTP_PASSWORD is not set in .env."

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        return True, "SMTP connection and authentication successful."
    except smtplib.SMTPAuthenticationError:
        return False, "SMTP authentication failed. Check your Gmail App Password and 2-Step Verification settings."
    except smtplib.SMTPConnectError as exc:
        return False, f"Could not connect to SMTP server ({settings.SMTP_HOST}:{settings.SMTP_PORT}): {exc}"
    except OSError as exc:
        return False, f"Network error connecting to {settings.SMTP_HOST}:{settings.SMTP_PORT}: {exc}"
    except Exception as exc:
        return False, f"SMTP verification failed: {exc}"


# ─── Verification email ───────────────────────────────────────────────────────

def send_verification_email(to_email: str, name: str, token: str) -> Tuple[bool, str | None]:
    """
    Send an email containing a one-click verification link.
    The link points to APP_BASE_URL/verify-email?token=<token>.
    """
    verify_url = f"{settings.APP_BASE_URL.rstrip('/')}/verify-email?token={token}"
    subject = "Verify your SocialProof email address"

    text_body = f"""Hi {name},

Please verify your email address by clicking the link below:

{verify_url}

This link expires in {settings.VERIFICATION_TOKEN_EXPIRE_MINUTES} minutes.

If you did not create a SocialProof account, you can safely ignore this email.

— The SocialProof Team
"""

    html_body = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:Arial,sans-serif;background:#f9fafb;margin:0;padding:0;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f9fafb;padding:40px 0;">
    <tr><td align="center">
      <table width="540" cellpadding="0" cellspacing="0"
             style="background:#ffffff;border-radius:12px;padding:40px;box-shadow:0 2px 12px rgba(0,0,0,.08);">
        <tr><td align="center" style="padding-bottom:24px;">
          <div style="width:56px;height:56px;background:#059669;border-radius:50%;
                      display:inline-flex;align-items:center;justify-content:center;">
            <span style="color:#fff;font-size:28px;">✉</span>
          </div>
          <h1 style="color:#111827;font-size:22px;margin:16px 0 4px;">Verify your email address</h1>
          <p style="color:#6b7280;font-size:14px;margin:0;">Hi <strong>{name}</strong>, welcome to SocialProof!</p>
        </td></tr>
        <tr><td style="padding:0 0 24px;">
          <p style="color:#374151;font-size:15px;line-height:1.6;margin:0 0 24px;">
            Click the button below to verify your email address and activate your account.
            This link is valid for <strong>{settings.VERIFICATION_TOKEN_EXPIRE_MINUTES} minutes</strong>.
          </p>
          <div style="text-align:center;">
            <a href="{verify_url}"
               style="display:inline-block;background:#059669;color:#ffffff;
                      text-decoration:none;font-size:16px;font-weight:600;
                      padding:14px 36px;border-radius:8px;letter-spacing:.3px;">
              Verify Email Address
            </a>
          </div>
        </td></tr>
        <tr><td style="border-top:1px solid #e5e7eb;padding-top:20px;">
          <p style="color:#9ca3af;font-size:12px;margin:0;line-height:1.5;">
            If the button doesn't work, copy and paste this link into your browser:<br>
            <a href="{verify_url}" style="color:#059669;word-break:break-all;">{verify_url}</a>
          </p>
          <p style="color:#9ca3af;font-size:12px;margin:12px 0 0;">
            If you didn't create a SocialProof account, please ignore this email.
          </p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""

    return _send(to_email, subject, html_body, text_body)


# ─── Password reset email ─────────────────────────────────────────────────────

def send_password_reset_email(to_email: str, name: str, token: str) -> Tuple[bool, str | None]:
    """
    Send a password-reset email with a one-click link.
    The link points to APP_BASE_URL/reset-password?token=<token>.
    """
    reset_url = f"{settings.APP_BASE_URL.rstrip('/')}/reset-password?token={token}"
    subject = "Reset your SocialProof password"

    text_body = f"""Hi {name},

We received a request to reset your password. Click the link below:

{reset_url}

This link expires in {settings.PASSWORD_RESET_EXPIRE_MINUTES} minutes.

If you did not request a password reset, you can safely ignore this email.

— The SocialProof Team
"""

    html_body = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:Arial,sans-serif;background:#f9fafb;margin:0;padding:0;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f9fafb;padding:40px 0;">
    <tr><td align="center">
      <table width="540" cellpadding="0" cellspacing="0"
             style="background:#ffffff;border-radius:12px;padding:40px;box-shadow:0 2px 12px rgba(0,0,0,.08);">
        <tr><td align="center" style="padding-bottom:24px;">
          <div style="width:56px;height:56px;background:#d97706;border-radius:50%;
                      display:inline-flex;align-items:center;justify-content:center;">
            <span style="color:#fff;font-size:28px;">🔑</span>
          </div>
          <h1 style="color:#111827;font-size:22px;margin:16px 0 4px;">Reset your password</h1>
          <p style="color:#6b7280;font-size:14px;margin:0;">Hi <strong>{name}</strong></p>
        </td></tr>
        <tr><td style="padding:0 0 24px;">
          <p style="color:#374151;font-size:15px;line-height:1.6;margin:0 0 24px;">
            We received a request to reset your SocialProof password.
            Click the button below to set a new password.
            This link is valid for <strong>{settings.PASSWORD_RESET_EXPIRE_MINUTES} minutes</strong>.
          </p>
          <div style="text-align:center;">
            <a href="{reset_url}"
               style="display:inline-block;background:#d97706;color:#ffffff;
                      text-decoration:none;font-size:16px;font-weight:600;
                      padding:14px 36px;border-radius:8px;letter-spacing:.3px;">
              Reset Password
            </a>
          </div>
        </td></tr>
        <tr><td style="border-top:1px solid #e5e7eb;padding-top:20px;">
          <p style="color:#9ca3af;font-size:12px;margin:0;line-height:1.5;">
            If the button doesn't work, copy and paste this link into your browser:<br>
            <a href="{reset_url}" style="color:#d97706;word-break:break-all;">{reset_url}</a>
          </p>
          <p style="color:#9ca3af;font-size:12px;margin:12px 0 0;">
            If you didn't request a password reset, you can safely ignore this email.
            Your password will not change.
          </p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""

    return _send(to_email, subject, html_body, text_body)
