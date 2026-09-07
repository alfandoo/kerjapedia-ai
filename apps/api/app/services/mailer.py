from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage

from app.core.config import settings


def _otp_email_body(code: str) -> str:
    return f"""\
<!DOCTYPE html>
<html>
  <body style="margin:0;padding:0;background-color:#f0f8f2;font-family:'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#f0f8f2;padding:32px 16px;">
      <tr><td align="center">
        <table role="presentation" width="560" cellpadding="0" cellspacing="0" border="0" style="width:100%;max-width:560px;background-color:#ffffff;border:1px solid #d8e8dc;border-radius:16px;overflow:hidden;">
          <tr><td style="background-color:#176b3a;padding:20px 32px;color:#ffffff;font-size:17px;font-weight:700;">
            KerjaPedia AI &mdash; Email verification
          </td></tr>
          <tr><td style="padding:26px 32px 8px 32px;">
            <h1 style="margin:0 0 10px 0;font-size:20px;color:#14251b;">Confirm your email address</h1>
            <p style="margin:0 0 22px 0;font-size:14px;line-height:1.6;color:#567064;">
              Thank you for signing up for KerjaPedia. Use the code below to complete your registration.
            </p>
          </td></tr>
          <tr><td align="center" style="padding:0 32px;">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
              <tr><td align="center" style="background-color:#f0f8f2;border:2px dashed #9fc9ac;border-radius:12px;padding:24px 16px;">
                <p style="margin:0 0 6px 0;font-size:11px;letter-spacing:0.5px;color:#567064;">YOUR VERIFICATION CODE</p>
                <p style="margin:0;font-size:36px;font-weight:700;letter-spacing:10px;color:#104d2a;font-family:Consolas,'Courier New',monospace;">
                  {code}
                </p>
              </td></tr>
            </table>
          </td></tr>
          <tr><td style="padding:22px 32px 28px 32px;">
            <p style="margin:0;font-size:12px;line-height:1.6;color:#9aa8a0;">
              The code expires within {settings.email_otp_expiry_minutes} minutes and is single-use.
              If you didn't create this account, you can safely ignore this email.
            </p>
          </td></tr>
        </table>
      </td></tr>
    </table>
  </body>
</html>
"""


def send_verification_email(to_email: str, code: str) -> None:
    """Send a verification OTP email through the configured SMTP server."""
    if not settings.smtp_host or not settings.smtp_username or not settings.smtp_password:
        raise RuntimeError("SMTP is not configured.")
    sender = settings.smtp_sender_email or settings.smtp_username
    sender_name = settings.smtp_sender_name or "KerjaPedia"

    message = EmailMessage()
    message["Subject"] = "Your KerjaPedia verification code"
    message["From"] = f"{sender_name} <{sender}>"
    message["To"] = to_email
    message.set_content(
        f"Your KerjaPedia verification code is {code}. "
        f"Enter it to complete registration. Expires within "
        f"{settings.email_otp_expiry_minutes} minutes."
    )
    message.add_alternative(_otp_email_body(code), subtype="html")

    port = settings.smtp_port
    context = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(settings.smtp_host, port, context=context, timeout=30) as smtp:
            smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(message)
    else:
        with smtplib.SMTP(settings.smtp_host, port, timeout=30) as smtp:
            if settings.smtp_use_tls:
                smtp.starttls(context=context)
            smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(message)
