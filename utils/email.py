"""Email utility for sending CSV exports."""

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from pathlib import Path


def send_csv_email(
    smtp_server: str,
    smtp_port: int,
    sender_email: str,
    sender_password: str,
    recipients: str,
    csv_filepath: str,
    project: str = "ecoflow",
    item_count: int = 0
) -> tuple[bool, str]:
    """Send CSV file via email.

    Args:
        smtp_server: SMTP server address
        smtp_port: SMTP port (usually 587 for TLS)
        sender_email: Sender email address
        sender_password: Sender email password/app password
        recipients: Comma-separated list of recipient emails
        csv_filepath: Path to the CSV file to attach
        project: Project name for email subject
        item_count: Number of items in the export

    Returns:
        Tuple of (success: bool, message: str)
    """
    try:
        # Parse recipients
        recipient_list = [r.strip() for r in recipients.split(",") if r.strip()]
        if not recipient_list:
            return False, "No recipients configured"

        # Create message
        msg = MIMEMultipart()
        msg["From"] = sender_email
        msg["To"] = ", ".join(recipient_list)
        msg["Subject"] = f"{project.capitalize()} Inventory Export - {item_count} items"

        # Email body
        body = f"""Inventory export from The-Uplink

Project: {project.capitalize()}
Items exported: {item_count}
File: {Path(csv_filepath).name}

This is an automated message.
"""
        msg.attach(MIMEText(body, "plain"))

        # Attach CSV file
        with open(csv_filepath, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                f"attachment; filename={Path(csv_filepath).name}"
            )
            msg.attach(part)

        # Send email
        with smtplib.SMTP(smtp_server, smtp_port, timeout=30) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, recipient_list, msg.as_string())

        return True, f"Email sent to {len(recipient_list)} recipient(s)"

    except smtplib.SMTPAuthenticationError:
        return False, "Authentication failed - check email/password"
    except smtplib.SMTPRecipientsRefused:
        return False, "Recipients refused - check email addresses"
    except smtplib.SMTPException as e:
        return False, f"SMTP error: {str(e)}"
    except FileNotFoundError:
        return False, "CSV file not found"
    except Exception as e:
        return False, f"Error: {str(e)}"


def test_email_connection(
    smtp_server: str,
    smtp_port: int,
    sender_email: str,
    sender_password: str
) -> tuple[bool, str]:
    """Test SMTP connection and authentication.

    Returns:
        Tuple of (success: bool, message: str)
    """
    try:
        with smtplib.SMTP(smtp_server, smtp_port, timeout=10) as server:
            server.starttls()
            server.login(sender_email, sender_password)
        return True, "Connection successful"
    except smtplib.SMTPAuthenticationError:
        return False, "Authentication failed - check email/password"
    except smtplib.SMTPException as e:
        return False, f"SMTP error: {str(e)}"
    except Exception as e:
        return False, f"Connection failed: {str(e)}"
