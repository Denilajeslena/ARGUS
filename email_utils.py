import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import secrets
import time

# In-memory token store (for demo)
RESET_TOKENS = {}

SMTP_SERVER = 'smtp.gmail.com'
SMTP_PORT = 587
SMTP_EMAIL = 'argusmp3@gmail.com'
SMTP_PASSWORD = 'nithu123456'

RESET_LINK_BASE = 'http://localhost:8501/?reset_token='


def send_reset_email(to_email, token):
    msg = MIMEMultipart()
    msg['From'] = SMTP_EMAIL
    msg['To'] = to_email
    msg['Subject'] = 'ARGUS Password Reset'
    link = f"{RESET_LINK_BASE}{token}"
    body = f"Click the link to reset your password: {link} (valid for 10 minutes)"
    msg.attach(MIMEText(body, 'plain'))
    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SMTP_EMAIL, SMTP_PASSWORD)
        server.sendmail(SMTP_EMAIL, to_email, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print('Email error:', e)
        return False


def generate_reset_token(email):
    token = secrets.token_urlsafe(24)
    RESET_TOKENS[token] = {'email': email, 'created': time.time()}
    return token


def verify_reset_token(token):
    data = RESET_TOKENS.get(token)
    if not data:
        return None
    # Token valid for 10 minutes
    if time.time() - data['created'] > 600:
        del RESET_TOKENS[token]
        return None
    return data['email']


def update_password(email, new_password, user_db):
    if email in user_db:
        user_db[email] = new_password
        return True
    return False
