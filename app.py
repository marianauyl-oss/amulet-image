# app.py
# -*- coding: utf-8 -*-
import os
from datetime import datetime
from functools import wraps

from flask import Flask, request, jsonify, send_from_directory, abort
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from sqlalchemy import text
import sqlalchemy as sa

# =========================
# Config
# =========================
APP_TITLE = "Amulet Image Admin"
DEFAULT_SQLITE = "sqlite:///amulet.db"

ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASS", "admin")

DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_SQLITE)

app = Flask(__name__, static_folder="static", static_url_path="")
app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
CORS(app, supports_credentials=True)

# =========================
# Models
# =========================
class License(db.Model):
    __tablename__ = "license"
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(128), unique=True, nullable=False)
    mac_id = db.Column(db.String(64), nullable=True)
    status = db.Column(db.String(50), default="active")  # active/inactive
    credit = db.Column(db.Integer, default=0)
    last_active = db.Column(db.DateTime, nullable=True)
    # колонка, якої раніше могло не бути:
    active = db.Column(db.Boolean, default=True)         # дублює status як простий прапор
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ApiKey(db.Model):
    __tablename__ = "apikey"
    id = db.Column(db.Integer, primary_key=True)
    api_key = db.Column(db.String(256), unique=True, nullable=False)
    status = db.Column(db.String(50), default="active")  # active/inactive
    in_use = db.Column(db.Boolean, default=False)
    last_used = db.Column(db.DateTime, nullable=True)
    note = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Config(db.Model):
    __tablename__ = "config"
    id = db.Column(db.Integer, primary_key=True)
    latest_version = db.Column(db.String(50), default="2.3.3")
    force_update = db.Column(db.Boolean, default=False)
    maintenance = db.Column(db.Boolean, default=False)
    maintenance_message = db.Column(db.Text, default="")
    update_description = db.Column(db.Text, default="")
    update_links = db.Column(db.Text, default="[]")  # зберігаємо JSON рядком
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Price(db.Model):
    __tablename__ = "price"
    id = db.Column(db.Integer, primary_key=True)
    model = db.Column(db.String(64), unique=True, nullable=False)
    price = db.Column(db.Integer, default=1)  # кредити за один запит
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# =========================
# Auth helper (very simple)
# =========================
def require_admin(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        auth = request.authorization
        if not auth or auth.username != ADMIN_USER or auth.password != ADMIN_PASS:
            return abort(401)
        return fn(*args, **kwargs)
    return wrapper


# =========================
# Static/Admin
# =========================
@app.route("/")
def root():
    return send_from_directory(app.static_folder, "admin.html")

@app.route("/admin")
def admin_page():
    return send_from_directory(app.static_folder, "admin.html")

@app.route("/admin.css")
def admin_css():
    return send_from_directory(app.static_folder, "admin.css")

@app.route("/admin.js")
def admin_js():
    return send_from_directory(app.static_folder, "admin.js")


# =========================
# Admin API
# =========================
@app.route("/admin_api/login", methods=["GET"])
@require_admin
def admin_api_login():
    return jsonify({"ok": True})


# ---- Licenses ----
@app.route("/admin_api/licenses", methods=["GET"])
@require_admin
def admin_licenses():
    q = License.query.order_by(License.id.desc()).all()
    return jsonify({
        "ok": True,
        "items": [
            {
                "id": x.id,
                "key": x.key,
                "mac_id": x.mac_id or "",
                "status": x.status or "",
                "active": bool(x.active),
                "credit": int(x.credit or 0),
                "last_active": (x.last_active.isoformat() if x.last_active else None),
                "created_at": (x.created_at.isoformat() if x.created_at else None),
                "updated_at": (x.updated_at.isoformat() if x.updated_at else None)
            } for x in q
        ]
    })

@app.route("/admin_api/licenses", methods=["POST"])
@require_admin
def admin_licenses_add():
    data = request.get_json(force=True, silent=True) or {}
    key = (data.get("key") or "").strip()
    credit = int(data.get("credit") or 0)
    status = (data.get("status") or "active").strip().lower()
    if not key:
        return jsonify({"ok": False, "msg": "key is required"}), 400
    if License.query.filter_by(key=key).first():
        return jsonify({"ok": False, "msg": "key already exists"}), 409
    item = License(key=key, credit=credit, status=status, active=(status == "active"))
    db.session.add(item)
    db.session.commit()
    return jsonify({"ok": True, "id": item.id})

@app.route("/admin_api/licenses/<int:lic_id>", methods=["DELETE"])
@require_admin
def admin_licenses_delete(lic_id: int):
    item = License.query.get(lic_id)
    if not item:
        return jsonify({"ok": False, "msg": "not found"}), 404
    db.session.delete(item)
    db.session.commit()
    return jsonify({"ok": True})


# ---- API Keys (включаючи масове завантаження з .txt) ----
@app.route("/admin_api/apikeys", methods=["GET"])
@require_admin
def admin_apikeys_list():
    items = ApiKey.query.order_by(ApiKey.id.desc()).all()
    return jsonify({
        "ok": True,
        "items": [
            {
                "id": x.id,
                "api_key": x.api_key,
                "status": x.status,
                "in_use": bool(x.in_use),
                "last_used": (x.last_used.isoformat() if x.last_used else None),
                "note": x.note or ""
            } for x in items
        ]
    })

@app.route("/admin_api/apikeys", methods=["POST"])
@require_admin
def admin_apikeys_add_single():
    data = request.get_json(force=True, silent=True) or {}
    api_key = (data.get("api_key") or "").strip()
    note = (data.get("note") or "").strip()
    if not api_key:
        return jsonify({"ok": False, "msg": "api_key is required"}), 400
    if ApiKey.query.filter_by(api_key=api_key).first():
        return jsonify({"ok": False, "msg": "already exists"}), 409
    item = ApiKey(api_key=api_key, status="active", in_use=False, note=note)
    db.session.add(item)
    db.session.commit()
    return jsonify({"ok": True, "id": item.id})

@app.route("/admin_api/apikeys/upload_txt", methods=["POST"])
@require_admin
def admin_apikeys_upload_txt():
    """
    Приймає raw text (multipart/form-data або text/plain або JSON {"text": "..."}):
    кожен рядок = окремий ключ. Пропускає дублікати.
    """
    text_payload = ""
    if request.files:
        f = request.files.get("file")
        if f:
            text_payload = f.read().decode("utf-8", errors="ignore")
    if not text_payload and request.is_json:
        text_payload = (request.get_json(silent=True) or {}).get("text", "")
    if not text_payload:
        text_payload = request.get_data(as_text=True)

    lines = [ln.strip() for ln in (text_payload or "").splitlines() if ln.strip()]
    if not lines:
        return jsonify({"ok": False, "msg": "no keys provided"}), 400

    added = 0
    for line in lines:
        if not ApiKey.query.filter_by(api_key=line).first():
            db.session.add(ApiKey(api_key=line, status="active"))
            added += 1
    db.session.commit()
    return jsonify({"ok": True, "added": added})


@app.route("/admin_api/apikeys/<int:key_id>", methods=["DELETE"])
@require_admin
def admin_apikeys_delete(key_id: int):
    item = ApiKey.query.get(key_id)
    if not item:
        return jsonify({"ok": False, "msg": "not found"}), 404
    db.session.delete(item)
    db.session.commit()
    return jsonify({"ok": True})


# ---- Config ----
@app.route("/admin_api/config", methods=["GET"])
@require_admin
def admin_config_get():
    cfg = Config.query.first()
    if not cfg:
        return jsonify({"ok": True, "config": {}})
    return jsonify({
        "ok": True,
        "config": {
            "latest_version": cfg.latest_version or "",
            "force_update": bool(cfg.force_update),
            "maintenance": bool(cfg.maintenance),
            "maintenance_message": cfg.maintenance_message or "",
            "update_description": cfg.update_description or "",
            "update_links": cfg.update_links or "[]",
            "updated_at": cfg.updated_at.isoformat() if cfg.updated_at else None,
        }
    })

@app.route("/admin_api/config", methods=["POST"])
@require_admin
def admin_config_set():
    data = request.get_json(force=True, silent=True) or {}
    cfg = Config.query.first()
    if not cfg:
        cfg = Config()
        db.session.add(cfg)

    def _bool(v):
        if isinstance(v, bool): return v
        s = str(v or "").strip().lower()
        return s in ("1", "true", "yes", "y", "on")

    if "latest_version" in data:       cfg.latest_version = str(data["latest_version"]).strip()
    if "force_update" in data:         cfg.force_update = _bool(data["force_update"])
    if "maintenance" in data:          cfg.maintenance = _bool(data["maintenance"])
    if "maintenance_message" in data:  cfg.maintenance_message = str(data["maintenance_message"])
    if "update_description" in data:   cfg.update_description = str(data["update_description"])
    if "update_links" in data:
        # приймаємо або список, або рядок JSON/CSV
        v = data["update_links"]
        if isinstance(v, list):
            import json as _json
            cfg.update_links = _json.dumps(v, ensure_ascii=False)
        else:
            cfg.update_links = str(v)
    cfg.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"ok": True})


# ---- Prices ----
DEFAULT_PRICES = {
    "seedream-v4": 1,
    "flux-dev": 1,
    "flux-pro-v1-1": 2,
    "gemini-2.5-flash": 1,
    "imagen3": 2,
    "classic-fast": 1,
}

@app.route("/admin_api/prices", methods=["GET"])
@require_admin
def admin_prices_get():
    items = Price.query.order_by(Price.model.asc()).all()
    return jsonify({
        "ok": True,
        "items": [{"id": x.id, "model": x.model, "price": int(x.price or 0)} for x in items]
    })

@app.route("/admin_api/prices", methods=["POST"])
@require_admin
def admin_prices_set():
    """
    JSON: {"items":[{"model":"seedream-v4","price":1}, ...]}
    Перезаписує/створює записи.
    """
    data = request.get_json(force=True, silent=True) or {}
    items = data.get("items") or []
    if not isinstance(items, list):
        return jsonify({"ok": False, "msg": "items must be list"}), 400

    for it in items:
        m = (it.get("model") or "").strip()
        try:
            p = int(it.get("price"))
        except Exception:
            p = None
        if not m or p is None or p < 0:
            continue
        row = Price.query.filter_by(model=m).first()
        if not row:
            row = Price(model=m, price=p)
            db.session.add(row)
        else:
            row.price = p
            row.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"ok": True})


# =========================
# Healthz
# =========================
@app.route("/healthz")
def healthz():
    return jsonify({"ok": True, "service": "amulet-image-admin"})


# =========================
# DB bootstrap + AUTOFIX (Postgres)
# =========================
def _ensure_pg_columns():
    """
    Простий «м’який» автопатч для PostgreSQL:
    додає відсутні колонки, якщо їх немає (без міграцій Alembic).
    Для SQLite нічого не робимо.
    """
    eng = db.engine
    if eng.dialect.name != "postgresql":
        return

    insp = sa.inspect(eng)

    def ensure(table: str, col_name: str, ddl: str):
        # якщо таблиці ще нема — create_all нижче її створить
        if not insp.has_table(table):
            return
        cols = {c["name"] for c in insp.get_columns(table)}
        if col_name not in cols:
            # важливо: IF NOT EXISTS, щоб не падало при гонці
            sql = f'ALTER TABLE "{table}" ADD COLUMN IF NOT EXISTS "{col_name}" {ddl}'
            with eng.begin() as conn:
                conn.execute(text(sql))

    # --- config ---
    ensure("config", "latest_version",       "VARCHAR(50) DEFAULT '2.3.3'")
    ensure("config", "force_update",         "BOOLEAN DEFAULT FALSE")
    ensure("config", "maintenance",          "BOOLEAN DEFAULT FALSE")
    ensure("config", "maintenance_message",  "TEXT DEFAULT ''")
    ensure("config", "update_description",   "TEXT DEFAULT ''")
    ensure("config", "update_links",         "TEXT DEFAULT '[]'")
    ensure("config", "updated_at",           "TIMESTAMPTZ DEFAULT NOW()")

    # --- license ---
    ensure("license", "mac_id",      "VARCHAR(64)")
    ensure("license", "status",      "VARCHAR(50) DEFAULT 'active'")
    ensure("license", "credit",      "INTEGER DEFAULT 0")
    ensure("license", "last_active", "TIMESTAMPTZ")
    ensure("license", "active",      "BOOLEAN DEFAULT TRUE")
    ensure("license", "created_at",  "TIMESTAMPTZ DEFAULT NOW()")
    ensure("license", "updated_at",  "TIMESTAMPTZ DEFAULT NOW()")

    # --- apikey ---
    ensure("apikey", "status",     "VARCHAR(50) DEFAULT 'active'")
    ensure("apikey", "in_use",     "BOOLEAN DEFAULT FALSE")
    ensure("apikey", "last_used",  "TIMESTAMPTZ")
    ensure("apikey", "note",       "TEXT")
    ensure("apikey", "created_at", "TIMESTAMPTZ DEFAULT NOW()")
    ensure("apikey", "updated_at", "TIMESTAMPTZ DEFAULT NOW()")

    # --- price ---
    ensure("price", "model",      "VARCHAR(64)")
    ensure("price", "price",      "INTEGER DEFAULT 1")
    ensure("price", "created_at", "TIMESTAMPTZ DEFAULT NOW()")
    ensure("price", "updated_at", "TIMESTAMPTZ DEFAULT NOW()")


with app.app_context():
    # створюємо таблиці згідно моделей (якщо їх ще немає)
    db.create_all()

    # >>> ВАЖЛИВО: автододавання відсутніх колонок у PostgreSQL <<<
    _ensure_pg_columns()

    # seed Config
    if not Config.query.first():
        db.session.add(Config(
            latest_version="2.3.3",
            force_update=False,
            maintenance=False,
            maintenance_message="",
            update_description="",
            update_links="[]",
            updated_at=datetime.utcnow()
        ))
        db.session.commit()

    # seed Prices (якщо порожньо)
    if Price.query.count() == 0:
        for m, p in DEFAULT_PRICES.items():
            db.session.add(Price(model=m, price=p))
        db.session.commit()


# =========================
# WSGI entry (Render runs gunicorn app:app)
# =========================
if __name__ == "__main__":
    # Локально:
    #   export FLASK_ENV=development
    #   python app.py
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True)