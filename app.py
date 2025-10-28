# -*- coding: utf-8 -*-
import os
import hmac
from datetime import datetime
from functools import wraps

from flask import Flask, jsonify, request, Response, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from sqlalchemy import text
from sqlalchemy import inspect

# =========================
# App & Config
# =========================
app = Flask(__name__, static_folder="static", static_url_path="/")
CORS(app)

# ---- DATABASE_URL (Postgres через psycopg3) ----
_db_url = os.getenv("DATABASE_URL", "").strip()
if not _db_url:
    # Локальний фолбек (SQLite)
    _db_url = "sqlite:///amulet.db"
# Якщо це звичайний Postgres URL без драйвера — додамо драйвер psycopg
if _db_url.startswith("postgresql://"):
    _db_url = _db_url.replace("postgresql://", "postgresql+psycopg://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = _db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# =========================
# Helpers
# =========================
ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASS", "admin")

def safe_str_cmp(a, b):
    return hmac.compare_digest(str(a), str(b))

def require_admin_auth(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Basic "):
            try:
                import base64
                u, p = base64.b64decode(auth.split()[1]).decode("utf-8").split(":", 1)
            except Exception:
                u = p = ""
            if safe_str_cmp(u, ADMIN_USER) and safe_str_cmp(p, ADMIN_PASS):
                return fn(*args, **kwargs)
        return Response("Unauthorized", 401, {"WWW-Authenticate": 'Basic realm="Admin"'})
    return wrapper

def now_utc_str():
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"

# =========================
# Models
# =========================
class License(db.Model):
    __tablename__ = "license"
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(120), unique=True, nullable=False, index=True)
    mac_id = db.Column(db.String(64), nullable=True, index=True)
    status = db.Column(db.String(32), nullable=False, default="active")  # active/inactive
    credit = db.Column(db.Integer, nullable=False, default=0)
    last_active = db.Column(db.DateTime, nullable=True)
    # для зворотної сумісності з UI, де інколи зверталися до license.active
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=db.func.now(),
        onupdate=db.func.now()
    )

class ApiKey(db.Model):
    __tablename__ = "apikey"
    id = db.Column(db.Integer, primary_key=True)
    api_key = db.Column(db.String(200), unique=True, nullable=False)
    status = db.Column(db.String(32), nullable=False, default="active")  # active/inactive
    in_use = db.Column(db.Boolean, nullable=False, default=False)
    last_used = db.Column(db.DateTime, nullable=True)
    note = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=db.func.now(),
        onupdate=db.func.now()
    )

class Config(db.Model):
    __tablename__ = "config"
    id = db.Column(db.Integer, primary_key=True)
    latest_version = db.Column(db.String(40), nullable=False, default="2.3.3")
    force_update = db.Column(db.Boolean, nullable=False, default=False)
    maintenance = db.Column(db.Boolean, nullable=False, default=False)
    maintenance_message = db.Column(db.Text, nullable=True)
    update_description = db.Column(db.Text, nullable=True)
    update_links = db.Column(db.Text, nullable=True)  # JSON text
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=db.func.now(),
        onupdate=db.func.now()
    )

class Price(db.Model):
    __tablename__ = "price"
    id = db.Column(db.Integer, primary_key=True)
    model = db.Column(db.String(80), unique=True, nullable=False, index=True)
    price = db.Column(db.Integer, nullable=False, default=1)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=db.func.now(),
        onupdate=db.func.now()
    )

class ActivityLog(db.Model):
    __tablename__ = "activitylog"
    id = db.Column(db.Integer, primary_key=True)
    action = db.Column(db.String(120), nullable=False)
    details = db.Column(db.Text, nullable=True)
    ip = db.Column(db.String(64), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())

# =========================
# Auto schema ensure (Postgres)
# =========================
def _ensure_column(table: str, col_sql: str):
    """
    Безпечне додавання колонки, якщо її немає.
    col_sql — фрагмент "ADD COLUMN ..." без слова ALTER TABLE.
    """
    try:
        db.session.execute(text(f'ALTER TABLE "{table}" {col_sql}'))
        db.session.commit()
    except Exception:
        db.session.rollback()

def _ensure_base_schema():
    """Створює таблиці та додає відсутні колонки (особливо updated_at)."""
    db.create_all()

    insp = inspect(db.engine)

    # ----- license -----
    if "license" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("license")}
        if "active" not in cols:
            _ensure_column("license", 'ADD COLUMN active BOOLEAN NOT NULL DEFAULT TRUE')
        if "created_at" not in cols:
            _ensure_column("license", 'ADD COLUMN created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()')
        if "updated_at" not in cols:
            _ensure_column("license", 'ADD COLUMN updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()')

    # ----- apikey -----
    if "apikey" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("apikey")}
        if "in_use" not in cols:
            _ensure_column("apikey", 'ADD COLUMN in_use BOOLEAN NOT NULL DEFAULT FALSE')
        if "last_used" not in cols:
            _ensure_column("apikey", 'ADD COLUMN last_used TIMESTAMPTZ')
        if "note" not in cols:
            _ensure_column("apikey", 'ADD COLUMN note VARCHAR(255)')
        if "created_at" not in cols:
            _ensure_column("apikey", 'ADD COLUMN created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()')
        if "updated_at" not in cols:
            _ensure_column("apikey", 'ADD COLUMN updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()')

    # ----- config -----
    if "config" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("config")}
        if "latest_version" not in cols:
            _ensure_column("config", 'ADD COLUMN latest_version VARCHAR(40) NOT NULL DEFAULT \'2.3.3\'')
        if "force_update" not in cols:
            _ensure_column("config", 'ADD COLUMN force_update BOOLEAN NOT NULL DEFAULT FALSE')
        if "maintenance" not in cols:
            _ensure_column("config", 'ADD COLUMN maintenance BOOLEAN NOT NULL DEFAULT FALSE')
        if "maintenance_message" not in cols:
            _ensure_column("config", 'ADD COLUMN maintenance_message TEXT')
        if "update_description" not in cols:
            _ensure_column("config", 'ADD COLUMN update_description TEXT')
        if "update_links" not in cols:
            _ensure_column("config", 'ADD COLUMN update_links TEXT')
        if "created_at" not in cols:
            _ensure_column("config", 'ADD COLUMN created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()')
        if "updated_at" not in cols:
            _ensure_column("config", 'ADD COLUMN updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()')

    # ----- price -----
    if "price" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("price")}
        if "updated_at" not in cols:
            _ensure_column("price", 'ADD COLUMN updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()')

    # ---- seed defaults ----
    if not Config.query.first():
        db.session.add(Config(
            latest_version="2.3.3",
            force_update=False,
            maintenance=False,
            maintenance_message="",
            update_description="",
            update_links="[]"
        ))
        db.session.commit()

    if Price.query.count() == 0:
        defaults = {
            "seedream-v4": 1,
            "flux-dev": 1,
            "flux-pro-v1-1": 2,
            "gemini-2.5-flash": 1,
            "imagen3": 2,
            "classic-fast": 1,
        }
        db.session.add_all([Price(model=m, price=v) for m, v in defaults.items()])
        db.session.commit()

# =========================
# Routes — UI
# =========================
@app.route("/")
def root_ok():
    return jsonify(ok=True, service="Amulet Image Backend", time=now_utc_str())

@app.route("/admin")
def admin_page():
    # віддаємо static/admin.html
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
@app.route("/admin_api/login")
@require_admin_auth
def admin_login():
    return jsonify(ok=True, user=ADMIN_USER)

# ---- Licenses ----
@app.route("/admin_api/licenses", methods=["GET"])
@require_admin_auth
def admin_licenses_list():
    q = License.query.order_by(License.id.desc()).all()
    out = []
    for x in q:
        out.append({
            "id": x.id,
            "key": x.key,
            "mac_id": x.mac_id,
            "status": x.status,
            "active": bool(x.active),
            "credit": x.credit,
            "last_active": x.last_active.isoformat() if x.last_active else None,
            "created_at": x.created_at.isoformat() if x.created_at else None,
            "updated_at": x.updated_at.isoformat() if x.updated_at else None,
        })
    return jsonify(items=out)

@app.route("/admin_api/licenses", methods=["POST"])
@require_admin_auth
def admin_license_create():
    data = request.get_json(force=True, silent=True) or {}
    key = (data.get("key") or "").strip()
    if not key:
        return jsonify(ok=False, msg="Missing key"), 400
    if License.query.filter_by(key=key).first():
        return jsonify(ok=False, msg="Key exists"), 400
    lic = License(
        key=key,
        mac_id=(data.get("mac_id") or "").strip() or None,
        status=(data.get("status") or "active").strip(),
        active=bool(data.get("active", True)),
        credit=int(data.get("credit") or 0),
        last_active=None
    )
    db.session.add(lic)
    db.session.commit()
    db.session.add(ActivityLog(action="license.create", details=f"key={key}", ip=request.remote_addr))
    db.session.commit()
    return jsonify(ok=True, id=lic.id)

@app.route("/admin_api/licenses/<int:lic_id>", methods=["PATCH"])
@require_admin_auth
def admin_license_update(lic_id):
    data = request.get_json(force=True, silent=True) or {}
    lic = License.query.get_or_404(lic_id)
    if "mac_id" in data:
        lic.mac_id = (data.get("mac_id") or "").strip() or None
    if "status" in data:
        lic.status = (data.get("status") or "active").strip()
    if "active" in data:
        lic.active = bool(data.get("active"))
    if "credit" in data:
        try:
            lic.credit = int(data.get("credit"))
        except Exception:
            pass
    db.session.commit()
    db.session.add(ActivityLog(action="license.update", details=f"id={lic_id}", ip=request.remote_addr))
    db.session.commit()
    return jsonify(ok=True)

@app.route("/admin_api/licenses/<int:lic_id>", methods=["DELETE"])
@require_admin_auth
def admin_license_delete(lic_id):
    lic = License.query.get_or_404(lic_id)
    db.session.delete(lic)
    db.session.commit()
    db.session.add(ActivityLog(action="license.delete", details=f"id={lic_id}", ip=request.remote_addr))
    db.session.commit()
    return jsonify(ok=True)

# ---- API Keys ----
@app.route("/admin_api/apikeys", methods=["GET"])
@require_admin_auth
def admin_apikeys_list():
    rows = ApiKey.query.order_by(ApiKey.id.desc()).all()
    out = []
    for x in rows:
        out.append({
            "id": x.id,
            "api_key": x.api_key,
            "status": x.status,
            "in_use": bool(x.in_use),
            "last_used": x.last_used.isoformat() if x.last_used else None,
            "note": x.note,
            "updated_at": x.updated_at.isoformat() if x.updated_at else None
        })
    return jsonify(items=out)

@app.route("/admin_api/apikeys", methods=["POST"])
@require_admin_auth
def admin_apikey_add():
    data = request.get_json(force=True, silent=True) or {}
    api_key = (data.get("api_key") or "").strip()
    if not api_key:
        return jsonify(ok=False, msg="Missing api_key"), 400
    if ApiKey.query.filter_by(api_key=api_key).first():
        return jsonify(ok=False, msg="Exists"), 400
    row = ApiKey(
        api_key=api_key,
        status=(data.get("status") or "active").strip(),
        in_use=bool(data.get("in_use", False)),
        note=(data.get("note") or "").strip() or None
    )
    db.session.add(row)
    db.session.commit()
    db.session.add(ActivityLog(action="apikey.create", details=f"key=***{api_key[-4:]}", ip=request.remote_addr))
    db.session.commit()
    return jsonify(ok=True, id=row.id)

@app.route("/admin_api/apikeys/<int:row_id>", methods=["PATCH"])
@require_admin_auth
def admin_apikey_update(row_id):
    data = request.get_json(force=True, silent=True) or {}
    row = ApiKey.query.get_or_404(row_id)
    if "status" in data:
        row.status = (data.get("status") or "active").strip()
    if "in_use" in data:
        row.in_use = bool(data.get("in_use"))
    if "note" in data:
        row.note = (data.get("note") or "").strip() or None
    db.session.commit()
    db.session.add(ActivityLog(action="apikey.update", details=f"id={row_id}", ip=request.remote_addr))
    db.session.commit()
    return jsonify(ok=True)

@app.route("/admin_api/apikeys/<int:row_id>", methods=["DELETE"])
@require_admin_auth
def admin_apikey_delete(row_id):
    row = ApiKey.query.get_or_404(row_id)
    db.session.delete(row)
    db.session.commit()
    db.session.add(ActivityLog(action="apikey.delete", details=f"id={row_id}", ip=request.remote_addr))
    db.session.commit()
    return jsonify(ok=True)

# ---- Config ----
@app.route("/admin_api/config", methods=["GET"])
@require_admin_auth
def admin_get_config():
    cfg = Config.query.first()
    return jsonify(ok=True, config={
        "latest_version": cfg.latest_version,
        "force_update": bool(cfg.force_update),
        "maintenance": bool(cfg.maintenance),
        "maintenance_message": cfg.maintenance_message or "",
        "update_description": cfg.update_description or "",
        "update_links": cfg.update_links or "[]",
        "updated_at": cfg.updated_at.isoformat() if cfg.updated_at else None
    })

@app.route("/admin_api/config", methods=["POST"])
@require_admin_auth
def admin_set_config():
    data = request.get_json(force=True, silent=True) or {}
    cfg = Config.query.first()
    if "latest_version" in data:
        cfg.latest_version = str(data.get("latest_version") or "").strip() or cfg.latest_version
    if "force_update" in data:
        cfg.force_update = bool(data.get("force_update"))
    if "maintenance" in data:
        cfg.maintenance = bool(data.get("maintenance"))
    if "maintenance_message" in data:
        cfg.maintenance_message = data.get("maintenance_message") or ""
    if "update_description" in data:
        cfg.update_description = data.get("update_description") or ""
    if "update_links" in data:
        # очікуємо JSON-рядок або масив; збережемо як текст
        import json
        links = data.get("update_links")
        if isinstance(links, list):
            cfg.update_links = json.dumps(links, ensure_ascii=False)
        else:
            cfg.update_links = str(links or "[]")
    db.session.commit()
    db.session.add(ActivityLog(action="config.update", details="", ip=request.remote_addr))
    db.session.commit()
    return jsonify(ok=True)

# ---- Prices ----
@app.route("/admin_api/prices", methods=["GET"])
@require_admin_auth
def admin_prices_list():
    rows = Price.query.order_by(Price.model.asc()).all()
    return jsonify(ok=True, prices=[{"id": r.id, "model": r.model, "price": r.price,
                                     "updated_at": r.updated_at.isoformat() if r.updated_at else None}
                                    for r in rows])

@app.route("/admin_api/prices", methods=["POST"])
@require_admin_auth
def admin_prices_upsert_bulk():
    """
    Очікує: { prices: [{model, price}, ...] }
    """
    data = request.get_json(force=True, silent=True) or {}
    items = data.get("prices") or []
    if not isinstance(items, list) or not items:
        return jsonify(ok=False, msg="No items"), 400
    touched = 0
    for it in items:
        model = str(it.get("model") or "").strip()
        try:
            price_val = int(it.get("price"))
        except Exception:
            continue
        if not model or price_val <= 0:
            continue
        row = Price.query.filter_by(model=model).first()
        if row:
            row.price = price_val
        else:
            row = Price(model=model, price=price_val)
            db.session.add(row)
        touched += 1
    db.session.commit()
    db.session.add(ActivityLog(action="price.bulk_upsert", details=f"count={touched}", ip=request.remote_addr))
    db.session.commit()
    return jsonify(ok=True, touched=touched)

@app.route("/admin_api/prices/<int:row_id>", methods=["PATCH"])
@require_admin_auth
def admin_price_update_one(row_id):
    data = request.get_json(force=True, silent=True) or {}
    row = Price.query.get_or_404(row_id)
    if "price" in data:
        try:
            val = int(data.get("price"))
            if val > 0:
                row.price = val
        except Exception:
            pass
    db.session.commit()
    db.session.add(ActivityLog(action="price.update", details=f"id={row_id}", ip=request.remote_addr))
    db.session.commit()
    return jsonify(ok=True)

# ---- Logs ----
@app.route("/admin_api/logs", methods=["GET"])
@require_admin_auth
def admin_logs_list():
    lim = max(1, min(int(request.args.get("limit", 200)), 1000))
    rows = ActivityLog.query.order_by(ActivityLog.id.desc()).limit(lim).all()
    return jsonify(items=[{
        "id": r.id,
        "action": r.action,
        "details": r.details,
        "ip": r.ip,
        "created_at": r.created_at.isoformat() if r.created_at else None
    } for r in rows])

# =========================
# Error handling
# =========================
@app.errorhandler(404)
def _404(_e):
    return jsonify(ok=False, error="Not Found"), 404

@app.errorhandler(500)
def _500(e):
    return jsonify(ok=False, error="Internal Server Error", detail=str(e)), 500

# =========================
# App bootstrap
# =========================
with app.app_context():
    _ensure_base_schema()

# =========================
# Dev server
# =========================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True)