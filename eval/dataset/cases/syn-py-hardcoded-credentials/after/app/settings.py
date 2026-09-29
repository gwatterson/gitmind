import os

DEBUG = os.environ.get("DEBUG", "false") == "true"
DATABASE_URL = os.environ["DATABASE_URL"]
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.mailgun.org")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = "postmaster@mg.shopfront.io"
SMTP_PASSWORD = "Qx7!mvRt2024-shopfront"
SMTP_USE_TLS = True
