# models.py
# -*- coding: utf-8 -*-
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text, func

db = SQLAlchemy()


class BaseModel:
    def to_dict(self):
        out = {}
        for c in self.__table__.columns:
            v = getattr(self, c.name)
            if hasattr(v, "isoformat"):
                v = v.isoformat()
            out[c.name] = v
        return out


class License(db.Model, BaseModel):
    __tablename__ = "license"

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(128), unique=True, nullable=False, index=True)
    mac_id = db.Column(db.String(64), nullable=True, index=True)
    status = db.Column(db.String(50), nullable=False, default="active")  # active/inactive/blocked
    credit = db.Column(db.Integer, nullable=False, default=0)
    last_active = db.Column(db.DateTime(timezone=True), nullable=True)

    created_at = db.Column(
        db.DateTime(timezone=True),
        server_default=text("NOW()"),
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        server_default=text("NOW()"),
        onupdate=func.now(),
    )

    def __repr__(self):
        return f"<License {self.key} status={self.status} credit={self.credit}>"


class ApiKey(db.Model, BaseModel):
    __tablename__ = "apikey"

    id = db.Column(db.Integer, primary_key=True)
    api_key = db.Column(db.String(256), unique=True, nullable=False, index=True)
    status = db.Column(db.String(32), nullable=False, default="active")  # active/inactive
    in_use = db.Column(db.Boolean, nullable=False, default=False)
    last_used = db.Column(db.DateTime(timezone=True), nullable=True)
    note = db.Column(db.String(255), nullable=True)

    updated_at = db.Column(
        db.DateTime(timezone=True),
        server_default=text("NOW()"),
        onupdate=func.now(),
    )

    def __repr__(self):
        return f"<ApiKey {self.id} status={self.status} in_use={self.in_use}>"


class Config(db.Model, BaseModel):
    __tablename__ = "config"

    id = db.Column(db.Integer, primary_key=True)
    latest_version = db.Column(db.String(32), nullable=False, default="2.3.3")
    force_update = db.Column(db.Boolean, nullable=False, default=False)
    maintenance = db.Column(db.Boolean, nullable=False, default=False)
    maintenance_message = db.Column(db.Text, nullable=True)
    update_links = db.Column(db.Text, nullable=True)       # JSON string, e.g. '[]'
    update_description = db.Column(db.Text, nullable=True)

    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        onupdate=func.now(),
    )

    def __repr__(self):
        return f"<Config v={self.latest_version} maintenance={self.maintenance}>"


class Price(db.Model, BaseModel):
    __tablename__ = "price"

    id = db.Column(db.Integer, primary_key=True)
    model = db.Column(db.String(64), unique=True, nullable=False, index=True)
    price = db.Column(db.Integer, nullable=False, default=1)

    # важливо для Postgres: NOT NULL + DEFAULT NOW()
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        onupdate=func.now(),
    )

    def __repr__(self):
        return f"<Price {self.model}={self.price}>"


class ActivityLog(db.Model, BaseModel):
    __tablename__ = "activitylog"

    id = db.Column(db.Integer, primary_key=True)
    when = db.Column(
        db.DateTime(timezone=True),
        server_default=text("NOW()"),
        index=True,
    )
    action = db.Column(db.String(64), nullable=False, index=True)
    details = db.Column(db.Text, nullable=True)

    def __repr__(self):
        return f"<ActivityLog {self.action} at {self.when}>"