from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Index, func

db = SQLAlchemy()

def utcnow():
    return datetime.utcnow()

class TimestampMixin:
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False)

class License(db.Model, TimestampMixin):
    __tablename__ = "license"
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(80), unique=True, index=True, nullable=False)
    mac_id = db.Column(db.String(64), index=True)
    status = db.Column(db.String(32), default="active", index=True, nullable=False)  # active/inactive/banned
    credit = db.Column(db.Integer, default=0, nullable=False)
    last_active = db.Column(db.DateTime)

    __table_args__ = (
        Index("ix_license_key_status", "key", "status"),
    )

class ApiKey(db.Model, TimestampMixin):
    __tablename__ = "apikey"
    id = db.Column(db.Integer, primary_key=True)
    api_key = db.Column(db.String(256), unique=True, index=True, nullable=False)
    status = db.Column(db.String(16), default="active", index=True)  # active/inactive
    in_use = db.Column(db.Boolean, default=False, nullable=False)
    last_used = db.Column(db.DateTime)
    note = db.Column(db.String(255))

class Config(db.Model, TimestampMixin):
    __tablename__ = "config"
    id = db.Column(db.Integer, primary_key=True)
    latest_version = db.Column(db.String(32), default="2.3.3")
    force_update = db.Column(db.Boolean, default=False)
    maintenance = db.Column(db.Boolean, default=False)
    maintenance_message = db.Column(db.String(500), default="")
    update_description = db.Column(db.Text, default="")
    update_links = db.Column(db.Text, default="[]")
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False)

class Price(db.Model, TimestampMixin):
    __tablename__ = "price"
    id = db.Column(db.Integer, primary_key=True)
    model = db.Column(db.String(80), unique=True, index=True, nullable=False)
    price = db.Column(db.Integer, nullable=False)

class ActivityLog(db.Model):
    __tablename__ = "activitylog"
    id = db.Column(db.Integer, primary_key=True)
    when = db.Column(db.DateTime, default=utcnow, index=True)
    event = db.Column(db.String(64), index=True)
    meta = db.Column(db.Text)  # JSON string