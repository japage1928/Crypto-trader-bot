"""Reusable email sender for daily trader bot summary."""
import os
import smtplib
import ssl
from email.message import EmailMessage
import logging

EMAIL_SUBJECT = "Daily Trader Bot Summary"
EMAIL_TO = "japage1928@icloud.com"

logger = logging.getLogger("emailer")


def send_email(summary_text: str):
    host = os.environ.get("EMAIL_HOST")
    port = int(os.environ.get("EMAIL_PORT", 465))
    username = os.environ.get("EMAIL_USERNAME")
    password = os.environ.get("EMAIL_PASSWORD")
    if not all([host, port, username, password]):
        logger.error("Email credentials missing in environment variables.")
        return False
    msg = EmailMessage()
    msg["Subject"] = EMAIL_SUBJECT
    msg["From"] = username
    msg["To"] = EMAIL_TO
    msg.set_content(summary_text)
    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(host, port, context=context) as server:
            server.login(username, password)
            server.send_message(msg)
        logger.info("Summary email sent successfully.")
        return True
    except Exception as e:
        logger.error(f"Failed to send summary email: {e}")
        return False
