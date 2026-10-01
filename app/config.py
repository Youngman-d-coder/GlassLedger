import os
from pathlib import Path
from datetime import timedelta

BASE = Path(__file__).resolve().parent.parent

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-change-me-before-production')
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', f"sqlite:///{BASE/'instance'/'inventory.db'}")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=int(os.getenv('SESSION_TIMEOUT_MINUTES', '30')))
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = os.getenv('COOKIE_SECURE', '0') == '1'
    BACKUP_DIR = os.getenv('BACKUP_DIR', str(BASE/'instance'/'backups'))
    REPORT_DIR = os.getenv('REPORT_DIR', str(BASE/'instance'/'reports'))
    GOOGLE_SERVICE_ACCOUNT_FILE = os.getenv('GOOGLE_SERVICE_ACCOUNT_FILE')
    GOOGLE_DRIVE_FOLDER_ID = os.getenv('GOOGLE_DRIVE_FOLDER_ID')
    AUTO_DRIVE_BACKUP = os.getenv('AUTO_DRIVE_BACKUP', '1') == '1'
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
    APP_VERSION = '1.0.0'
