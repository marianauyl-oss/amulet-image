# -*- coding: utf-8 -*-
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class License(db.Model):
    __tablename__ = "license"
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(255), unique=True, nullable=False)
    mac_id = db.Column(db.String(255))
    status = db.Column(db.String(50), default="active")
    credit = db.Column(db.Integer, default=0)
    last_active = db.Column(db.DateTime)
    # сумісність зі старими БД
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)

class ApiKey(db.Model):
    __tablename__ = "api_key"
    id = db.Column(db.Integer, primary_key=True)
    api_key = db.Column(db.String(255), unique=True, nullable=False)
    status = db.Column(db.String(50), default="active")
    in_use = db.Column(db.Boolean, default=False)
    last_used = db.Column(db.DateTime)
    note = db.Column(db.Text)

class Price(db.Model):
    __tablename__ = "price"
    id = db.Column(db.Integer, primary_key=True)
    model = db.Column(db.String(120), unique=True, nullable=False)
    price = db.Column(db.Integer, default=1, nullable=False)

class Config(db.Model):
    __tablename__ = "config"
    id = db.Column(db.Integer, primary_key=True)
    latest_version = db.Column(db.String(50), default="2.3.3")
    force_update = db.Column(db.Boolean, default=False)
    maintenance = db.Column(db.Boolean, default=False)
    maintenance_message = db.Column(db.Text, default="")
    update_description = db.Column(db.Text, default="")
    update_links = db.Column(db.Text, default="[]")
    updated_at = db.Column(db.DateTime)

class ActivityLog(db.Model):
    __tablename__ = "activity_log"
    id = db.Column(db.Integer, primary_key=True)
    license_id = db.Column(db.Integer)
    action = db.Column(db.String(50))
    char_count = db.Column(db.Integer, default=0)
    details = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

def init_db(app):
    db.init_app(app)
    with app.app_context():
        db.create_all()