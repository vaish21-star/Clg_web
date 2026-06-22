from flask import current_app
from flask_mail import Message

from enterprise.extensions import mail


def send_message(subject, recipients, body, html_body=None, sender=None):
    msg = Message(
        subject=subject,
        recipients=recipients if isinstance(recipients, list) else [recipients],
        body=body,
        html=html_body,
        sender=sender or current_app.config.get("MAIL_DEFAULT_SENDER"),
    )
    mail.send(msg)
    return True


def send_security_alert(recipient, subject, message):
    return send_message(subject=subject, recipients=[recipient], body=message)

