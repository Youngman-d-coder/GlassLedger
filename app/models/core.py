from datetime import datetime, timezone
from flask_login import UserMixin
from ..extensions import db

def utcnow():
    return datetime.now(timezone.utc)

class TimestampMixin:
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

class User(UserMixin, TimestampMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    display_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(30), nullable=False, default='OWNER')
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    last_login_at = db.Column(db.DateTime(timezone=True))

class LoginGuard(TimestampMixin, db.Model):
    __tablename__ = 'login_guards'
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(180), unique=True, nullable=False, index=True)
    failures = db.Column(db.Integer, nullable=False, default=0)
    locked_until = db.Column(db.DateTime(timezone=True))

class Category(TimestampMixin, db.Model):
    __tablename__ = 'categories'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    slug = db.Column(db.String(140), unique=True, nullable=False, index=True)
    description = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

class Unit(TimestampMixin, db.Model):
    __tablename__ = 'units'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    symbol = db.Column(db.String(20))
    unit_type = db.Column(db.String(30), nullable=False, default='COUNT')
    is_active = db.Column(db.Boolean, default=True, nullable=False)

class AppSetting(TimestampMixin, db.Model):
    __tablename__ = 'app_settings'
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(120), unique=True, nullable=False, index=True)
    value = db.Column(db.Text)

class Notification(TimestampMixin, db.Model):
    __tablename__ = 'notifications'
    id = db.Column(db.Integer, primary_key=True)
    level = db.Column(db.String(20), nullable=False, default='info')
    title = db.Column(db.String(160), nullable=False)
    message = db.Column(db.Text, nullable=False)
    link = db.Column(db.String(300))
    is_read = db.Column(db.Boolean, default=False, nullable=False)
    dedupe_key = db.Column(db.String(180), index=True)

class BackupRecord(TimestampMixin, db.Model):
    __tablename__ = 'backup_records'
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    storage = db.Column(db.String(30), nullable=False, default='LOCAL')
    size_bytes = db.Column(db.Integer)
    sha256 = db.Column(db.String(64))
    status = db.Column(db.String(30), default='HEALTHY')
    drive_file_id = db.Column(db.String(180))
    notes = db.Column(db.Text)
