"""Sends email notifications via SMTP.

Credentials come from environment variables (loaded from a local .env
file that is not committed) so they never end up in source control.
"""

import os
import smtplib
from email.mime.text import MIMEText

from dotenv import load_dotenv

load_dotenv()

SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")
EMAIL_TO = os.environ.get("EMAIL_TO", SMTP_USER)


def send_email(subject: str, body: str) -> None:
    if not SMTP_USER or not SMTP_PASSWORD:
        raise RuntimeError(
            "SMTP_USER / SMTP_PASSWORD are not set. Copy .env.example to .env "
            "and fill in your SMTP credentials."
        )

    message = MIMEText(body)
    message["Subject"] = subject
    message["From"] = SMTP_USER
    message["To"] = EMAIL_TO

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(SMTP_USER, [EMAIL_TO], message.as_string())
