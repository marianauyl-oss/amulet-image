from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class License(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(255), unique=True, nullable=False)
    mac_id = db.Column(db.String(255))
    credit = db.Column(db.Integer, default=0)
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)

class ApiKey(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    api_key = db.Column(db.String(255), unique=True, nullable=False)
    status = db.Column(db.String(50), default='active')

class Voice(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    voice_id = db.Column(db.String(255), unique=True, nullable=False)
    active = db.Column(db.Boolean, default=True)

class Config(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    latest_version = db.Column(db.String(50), default='1.0.0')
    force_update = db.Column(db.Boolean, default=False)
    maintenance = db.Column(db.Boolean, default=False)
    maintenance_message = db.Column(db.Text, default='')
    update_description = db.Column(db.Text, default='')
    update_links = db.Column(db.Text, default='')

class ActivityLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    license_id = db.Column(db.Integer, db.ForeignKey('license.id'), nullable=False)
    action = db.Column(db.String(50), nullable=False)
    char_count = db.Column(db.Integer, default=0)
    details = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
