# models.py
# -*- coding: utf-8 -*-
from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text

# імпортуйте з app: from models import db, License, ApiKey, Config, Price, ActivityLog
db = SQLAlchemy()


class License(db.Model):
    __tablename__ = "license"

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False, index=True)
    mac_id = db.Column(db.String(64), nullable=True, index=True)
    status = db.Column(db.String(16), nullable=False, default="active", index=True)
    credit = db.Column(db.Integer, nullable=False, default=0)
    last_active = db.Column(db.DateTime(timezone=True), nullable=True)

    def __repr__(self):
        return f"<License id={self.id} key={self.key} credit={self.credit}>"


class ApiKey(db.Model):
    __tablename__ = "api_key"

    id = db.Column(db.Integer, primary_key=True)
    api_key = db.Column(db.String(255), unique=True, nullable=False, index=True)
    status = db.Column(db.String(16), nullable=False, default="active", index=True)
    in_use = db.Column(db.Boolean, nullable=False, default=False)
    last_used = db.Column(db.DateTime(timezone=True), nullable=True)
    note = db.Column(db.Text, nullable=True)

    def __repr__(self):
        return f"<ApiKey id={self.id} status={self.status} in_use={self.in_use}>"


class Config(db.Model):
    __tablename__ = "config"

    id = db.Column(db.Integer, primary_key=True)
    latest_version = db.Column(db.String(32), nullable=False, default="2.3.3")
    force_update = db.Column(db.Boolean, nullable=False, default=False)
    maintenance = db.Column(db.Boolean, nullable=False, default=False)
    maintenance_message = db.Column(db.Text, nullable=True)
    update_links = db.Column(db.Text, nullable=True)          # JSON (array)
    update_description = db.Column(db.Text, nullable=True)
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=text("now()"),
    )

    def __repr__(self):
        return f"<Config v={self.latest_version} maint={self.maintenance}>"


class Price(db.Model):
    __tablename__ = "price"

    id = db.Column(db.Integer, primary_key=True)
    model = db.Column(db.String(64), unique=True, nullable=False, index=True)
    price = db.Column(db.Integer, nullable=False, default=1)
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=text("now()"),
    )

    def __repr__(self):
        return f"<Price {self.model}={self.price}>"


class ActivityLog(db.Model):
    __tablename__ = "activity_log"

    id = db.Column(db.Integer, primary_key=True)
    action = db.Column(db.String(64), nullable=False, index=True)
    details = db.Column(db.Text, nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=text("now()"),
        index=True,
    )

    def __repr__(self):
        return f"<Log {self.id} {self.action}>"