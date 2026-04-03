"""Email delivery for procurement digests.

Sends HTML digest emails via SMTP. Configured via environment variables:
    LOCALIZER_SMTP_HOST     - SMTP server hostname (default: smtp.gmail.com)
    LOCALIZER_SMTP_PORT     - SMTP port (default: 587)
    LOCALIZER_SMTP_USER     - SMTP username / sender email
    LOCALIZER_SMTP_PASS     - SMTP password or app password
    LOCALIZER_EMAIL_TO      - Recipient email(s), comma-separated
    LOCALIZER_EMAIL_FROM    - Sender display (default: same as SMTP_USER)
"""

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


def get_email_config() -> dict:
    """Read email config from environment variables."""
    return {
        "smtp_host": os.environ.get("LOCALIZER_SMTP_HOST", "smtp.gmail.com"),
        "smtp_port": int(os.environ.get("LOCALIZER_SMTP_PORT", "587")),
        "smtp_user": os.environ.get("LOCALIZER_SMTP_USER", ""),
        "smtp_pass": os.environ.get("LOCALIZER_SMTP_PASS", ""),
        "email_to": os.environ.get("LOCALIZER_EMAIL_TO", ""),
        "email_from": os.environ.get("LOCALIZER_EMAIL_FROM", ""),
    }


def send_digest_email(
    text_body: str,
    html_body: str,
    subject: str = "Localizer: New Procurement Opportunities",
    config: dict | None = None,
) -> bool:
    """Send the digest as a multipart email (text + HTML).

    Returns True on success, False on failure.
    """
    if config is None:
        config = get_email_config()

    smtp_user = config["smtp_user"]
    smtp_pass = config["smtp_pass"]
    email_to = config["email_to"]
    email_from = config.get("email_from") or smtp_user

    if not all([smtp_user, smtp_pass, email_to]):
        logger.error(
            "Email not configured. Set LOCALIZER_SMTP_USER, LOCALIZER_SMTP_PASS, "
            "and LOCALIZER_EMAIL_TO environment variables."
        )
        return False

    recipients = [addr.strip() for addr in email_to.split(",") if addr.strip()]

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = email_from
    msg["To"] = ", ".join(recipients)

    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(config["smtp_host"], config["smtp_port"]) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(smtp_user, smtp_pass)
            server.sendmail(email_from, recipients, msg.as_string())
        logger.info(f"Digest email sent to {', '.join(recipients)}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        return False
