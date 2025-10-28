# app.py
import os
import json
from datetime import datetime
from functools import wraps

from flask import (
    Flask, request, jsonify, send_from_directory, abort, Response, redirect, url_for
)
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from sqlalchemy import inspect, text
from sqlalchemy.sql import func

# =========================
# App & Config
# =========================
def _coerce_db_url(raw: str) -> str:
    if not raw:
        return ""
    raw = raw.strip()
    if raw.startswith("postgres://"):
        return raw.replace("postgres://", "postgresql+psycopg://", 1)
    if raw.startswith("postgresql://") and "+psycopg" not in raw:
        return raw.replace("postgresql://", "postgresql+psycopg://", 1)
    return raw

DATABASE_URL = _coerce_db_url(os.getenv("DATABASE_URL", "sqlite:///amulet.db"))
ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASS", "admin")

app = Flask(__name__, static_folder="static", static_url_path="/")
CORS(app)

app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["JSON_AS_ASCII"] = False

db = SQLAlchemy(app)


# =========================
# Models
# =========================
class License(db.Model):
    __tablename__ = "license"
    id          = db.Column(db.Integer, primary_key=True)
    key         = db.Column(db.String(64), unique=True, nullable=False, index=True)
    mac_id      = db.Column(db.String(32), default="", nullable=False)
    status      = db.Column(db.String(50), default="active", nullable=False)  # active/inactive
    credit      = db.Column(db.Integer, default=0, nullable=False)
    last_active = db.Column(db.DateTime, default=None)
    active      = db.Column(db.Boolean, default=True, nullable=False)  # дублюючий флаг (історична сумісність)
    created_at  = db.Column(db.DateTime, server_default=func.now(), nullable=False)
    updated_at  = db.Column(db.DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class ApiKey(db.Model):
    __tablename__ = "apikey"
    id         = db.Column(db.Integer, primary_key=True)
    api_key    = db.Column(db.Text, unique=True, nullable=False)
    status     = db.Column(db.String(50), default="active", nullable=False)  # active/inactive
    in_use     = db.Column(db.Boolean, default=False, nullable=False)
    last_used  = db.Column(db.DateTime, default=None)
    note       = db.Column(db.String(255), default="", nullable=False)
    created_at = db.Column(db.DateTime, server_default=func.now(), nullable=False)
    updated_at = db.Column(db.DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class Config(db.Model):
    __tablename__ = "config"
    id                   = db.Column(db.Integer, primary_key=True)
    latest_version       = db.Column(db.String(32), default="2.3.3", nullable=False)
    force_update         = db.Column(db.Boolean, default=False, nullable=False)
    maintenance          = db.Column(db.Boolean, default=False, nullable=False)
    maintenance_message  = db.Column(db.Text, default="", nullable=False)
    update_links         = db.Column(db.Text, default="[]", nullable=False)
    update_description   = db.Column(db.Text, default="", nullable=False)
    updated_at           = db.Column(db.DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class Price(db.Model):
    __tablename__ = "price"
    id     = db.Column(db.Integer, primary_key=True)
    model  = db.Column(db.String(64), unique=True, nullable=False, index=True)
    price  = db.Column(db.Integer, nullable=False, default=1)


class ActivityLog(db.Model):
    __tablename__ = "activitylog"
    id         = db.Column(db.Integer, primary_key=True)
    action     = db.Column(db.String(64), nullable=False)
    detail     = db.Column(db.Text, default="", nullable=False)
    created_at = db.Column(db.DateTime, server_default=func.now(), nullable=False)


# =========================
# Auto schema ensure BEFORE any queries
# =========================
DEFAULT_PRICES = {
    "seedream-v4": 1,
    "flux-dev": 1,
    "flux-pro-v1-1": 2,
    "gemini-2.5-flash": 1,
    "imagen3": 2,
    "classic-fast": 1,
}

def _add_column_if_missing(table_name: str, column_sql: str):
    """
    column_sql: e.g. 'updated_at TIMESTAMP DEFAULT NOW()'
    Works for Postgres (uses IF NOT EXISTS) and SQLite (manual check).
    """
    eng = db.engine
    dialect = eng.dialect.name

    insp = inspect(eng)
    cols = {c["name"] for c in insp.get_columns(table_name)} if insp.has_table(table_name) else set()
    col_name = column_sql.split()[0]
    if col_name in cols:
        return

    if dialect == "postgresql":
        # safe on PG
        ddl = f'ALTER TABLE "{table_name}" ADD COLUMN IF NOT EXISTS {column_sql};'
    else:
        # SQLite: no IF NOT EXISTS in older versions -> conditional branch already done
        ddl = f'ALTER TABLE "{table_name}" ADD COLUMN {column_sql};'

    with eng.begin() as conn:
        conn.execute(text(ddl))


def _ensure_base_schema():
    """Create tables and columns if missing. Seed defaults if needed."""
    db.create_all()

    # Ensure critical columns exist (for older DBs)
    # license
    _add_column_if_missing("license", "status VARCHAR(50) DEFAULT 'active'")
    _add_column_if_missing("license", "credit INTEGER DEFAULT 0")
    _add_column_if_missing("license", "mac_id VARCHAR(32) DEFAULT ''")
    _add_column_if_missing("license", "last_active TIMESTAMP NULL")
    _add_column_if_missing("license", "active BOOLEAN DEFAULT TRUE")
    _add_column_if_missing("license", "created_at TIMESTAMP DEFAULT NOW()")
    _add_column_if_missing("license", "updated_at TIMESTAMP DEFAULT NOW()")

    # apikey
    _add_column_if_missing("apikey", "status VARCHAR(50) DEFAULT 'active'")
    _add_column_if_missing("apikey", "in_use BOOLEAN DEFAULT FALSE")
    _add_column_if_missing("apikey", "last_used TIMESTAMP NULL")
    _add_column_if_missing("apikey", "note VARCHAR(255) DEFAULT ''")
    _add_column_if_missing("apikey", "created_at TIMESTAMP DEFAULT NOW()")
    _add_column_if_missing("apikey", "updated_at TIMESTAMP DEFAULT NOW()")

    # config
    _add_column_if_missing("config", "latest_version VARCHAR(32) DEFAULT '2.3.3'")
    _add_column_if_missing("config", "force_update BOOLEAN DEFAULT FALSE")
    _add_column_if_missing("config", "maintenance BOOLEAN DEFAULT FALSE")
    _add_column_if_missing("config", "maintenance_message TEXT DEFAULT ''")
    _add_column_if_missing("config", "update_links TEXT DEFAULT '[]'")
    _add_column_if_missing("config", "update_description TEXT DEFAULT ''")
    _add_column_if_missing("config", "updated_at TIMESTAMP DEFAULT NOW()")

    # price
    _add_column_if_missing("price", "model VARCHAR(64)")
    _add_column_if_missing("price", "price INTEGER DEFAULT 1")

    # Seed single config row
    if not Config.query.first():
        db.session.add(Config(
            latest_version="2.3.3",
            force_update=False,
            maintenance=False,
            maintenance_message="",
            update_links="[]",
            update_description=""
        ))
        db.session.commit()

    # Seed default prices if not present
    existing = {p.model: p for p in Price.query.all()}
    to_add = []
    for m, v in DEFAULT_PRICES.items():
        if m not in existing:
            to_add.append(Price(model=m, price=int(v)))
    if to_add:
        db.session.add_all(to_add)
        db.session.commit()


with app.app_context():
    _ensure_base_schema()


# =========================
# Helpers
# =========================
def log_action(action: str, detail: str = ""):
    try:
        db.session.add(ActivityLog(action=action, detail=detail))
        db.session.commit()
    except Exception:
        db.session.rollback()

def require_admin(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        auth = request.authorization
        if not auth or auth.username != ADMIN_USER or auth.password != ADMIN_PASS:
            return Response(
                "Auth required",
                401,
                {"WWW-Authenticate": 'Basic realm="Admin Area"'}
            )
        return fn(*args, **kwargs)
    return wrapper


# =========================
# Static / Admin UI
# =========================
@app.route("/")
def root():
    return redirect(url_for("admin"))

@app.route("/admin")
def admin():
    # static/admin.html
    return send_from_directory(app.static_folder, "admin.html")

@app.route("/admin.css")
def admin_css():
    return send_from_directory(app.static_folder, "admin.css")

@app.route("/admin.js")
def admin_js():
    return send_from_directory(app.static_folder, "admin.js")


# =========================
# Health
# =========================
@app.route("/healthz")
def healthz():
    return jsonify(ok=True, time=datetime.utcnow().isoformat())


# =========================
# Admin API
# =========================
@app.get("/admin_api/login")
@require_admin
def admin_login():
    return jsonify(ok=True)

# ---- Licenses ----
@app.get("/admin_api/licenses")
@require_admin
def admin_licenses_list():
    q = License.query
    status = request.args.get("status")
    if status:
        q = q.filter(License.status == status)
    key_like = request.args.get("q")
    if key_like:
        q = q.filter(License.key.ilike(f"%{key_like}%"))
    items = q.order_by(License.id.desc()).all()
    return jsonify([
        {
            "id": it.id,
            "key": it.key,
            "mac_id": it.mac_id,
            "status": it.status,
            "credit": it.credit,
            "last_active": it.last_active.isoformat() if it.last_active else None,
            "active": bool(it.active),
            "created_at": it.created_at.isoformat() if it.created_at else None,
            "updated_at": it.updated_at.isoformat() if it.updated_at else None
        } for it in items
    ])

@app.post("/admin_api/licenses")
@require_admin
def admin_licenses_create():
    """
    JSON:
      - key, credit, status
      - or keys_text: "KEY1\nKEY2\n..."
      - default credit=0, status=active
    """
    data = request.get_json(force=True, silent=True) or {}
    keys_text = (data.get("keys_text") or "").strip()
    created = []
    updated = []
    if keys_text:
        rows = [k.strip() for k in keys_text.splitlines() if k.strip()]
        for k in rows:
            it = License.query.filter_by(key=k).first()
            if it:
                updated.append(k)
            else:
                db.session.add(License(key=k, credit=int(data.get("credit", 0)), status=data.get("status", "active"), active=True))
                created.append(k)
        db.session.commit()
        log_action("license_bulk_add", json.dumps({"created": len(created), "updated_preexist": len(updated)}))
        return jsonify(ok=True, created=len(created), existed=len(updated))
    else:
        key = (data.get("key") or "").strip()
        if not key:
            return jsonify(ok=False, msg="key required"), 400
        credit = int(data.get("credit", 0))
        status = (data.get("status") or "active").strip() or "active"
        it = License.query.filter_by(key=key).first()
        if it:
            it.credit = credit
            it.status = status
            db.session.commit()
            log_action("license_update", key)
            return jsonify(ok=True, updated=True)
        db.session.add(License(key=key, credit=credit, status=status, active=True))
        db.session.commit()
        log_action("license_add", key)
        return jsonify(ok=True, created=True)

@app.delete("/admin_api/licenses/<int:lic_id>")
@require_admin
def admin_licenses_delete(lic_id: int):
    it = License.query.get(lic_id)
    if not it:
        return jsonify(ok=False, msg="not found"), 404
    db.session.delete(it)
    db.session.commit()
    log_action("license_delete", str(lic_id))
    return jsonify(ok=True)

# ---- API Keys ----
@app.get("/admin_api/apikeys")
@require_admin
def admin_apikeys_list():
    q = ApiKey.query.order_by(ApiKey.id.desc())
    return jsonify([
        {
            "id": it.id,
            "api_key": it.api_key,
            "status": it.status,
            "in_use": bool(it.in_use),
            "last_used": it.last_used.isoformat() if it.last_used else None,
            "note": it.note
        } for it in q.all()
    ])

@app.post("/admin_api/apikeys")
@require_admin
def admin_apikeys_add():
    """
    JSON:
      - api_key, note
      - or keys_text: "KEY1\nKEY2\n..." (масове додавання)
    """
    data = request.get_json(force=True, silent=True) or {}
    keys_text = (data.get("keys_text") or "").strip()
    created = 0
    existed = 0
    if keys_text:
        for line in keys_text.splitlines():
            k = line.strip()
            if not k:
                continue
            if ApiKey.query.filter_by(api_key=k).first():
                existed += 1
                continue
            db.session.add(ApiKey(api_key=k, status="active", in_use=False, note=data.get("note", "")))
            created += 1
        db.session.commit()
        log_action("apikey_bulk_add", json.dumps({"created": created, "existed": existed}))
        return jsonify(ok=True, created=created, existed=existed)
    api_key = (data.get("api_key") or "").strip()
    if not api_key:
        return jsonify(ok=False, msg="api_key required"), 400
    if ApiKey.query.filter_by(api_key=api_key).first():
        return jsonify(ok=False, msg="already exists"), 409
    note = (data.get("note") or "").strip()
    db.session.add(ApiKey(api_key=api_key, status="active", in_use=False, note=note))
    db.session.commit()
    log_action("apikey_add", api_key[:6] + "…")
    return jsonify(ok=True, created=True)

@app.delete("/admin_api/apikeys/<int:ak_id>")
@require_admin
def admin_apikeys_delete(ak_id: int):
    it = ApiKey.query.get(ak_id)
    if not it:
        return jsonify(ok=False, msg="not found"), 404
    db.session.delete(it)
    db.session.commit()
    log_action("apikey_delete", str(ak_id))
    return jsonify(ok=True)

@app.post("/admin_api/apikeys/deactivate/<int:ak_id>")
@require_admin
def admin_apikeys_deactivate(ak_id: int):
    it = ApiKey.query.get(ak_id)
    if not it:
        return jsonify(ok=False, msg="not found"), 404
    it.status = "inactive"
    it.in_use = False
    db.session.commit()
    log_action("apikey_deactivate", str(ak_id))
    return jsonify(ok=True)

# ---- Config ----
@app.get("/admin_api/config")
@require_admin
def admin_config_get():
    c = Config.query.first()
    return jsonify({
        "latest_version": c.latest_version,
        "force_update": bool(c.force_update),
        "maintenance": bool(c.maintenance),
        "maintenance_message": c.maintenance_message,
        "update_links": json.loads(c.update_links or "[]"),
        "update_description": c.update_description
    })

@app.post("/admin_api/config")
@require_admin
def admin_config_set():
    data = request.get_json(force=True, silent=True) or {}
    c = Config.query.first()
    if not c:
        c = Config()
        db.session.add(c)
    if "latest_version" in data:
        c.latest_version = str(data["latest_version"]).strip() or c.latest_version
    if "force_update" in data:
        c.force_update = bool(data["force_update"])
    if "maintenance" in data:
        c.maintenance = bool(data["maintenance"])
    if "maintenance_message" in data:
        c.maintenance_message = str(data["maintenance_message"] or "")
    if "update_links" in data:
        val = data["update_links"]
        if isinstance(val, list):
            c.update_links = json.dumps(val, ensure_ascii=False)
        elif isinstance(val, str):
            try:
                parsed = json.loads(val)
                if isinstance(parsed, list):
                    c.update_links = json.dumps(parsed, ensure_ascii=False)
                else:
                    c.update_links = json.dumps([val], ensure_ascii=False)
            except Exception:
                c.update_links = json.dumps([v.strip() for v in val.split(",") if v.strip()], ensure_ascii=False)
    if "update_description" in data:
        c.update_description = str(data["update_description"] or "")
    db.session.commit()
    log_action("config_update")
    return jsonify(ok=True)

# ---- Prices (Замість "voices" вкладки) ----
@app.get("/admin_api/prices")
@require_admin
def admin_prices_list():
    items = Price.query.order_by(Price.model.asc()).all()
    return jsonify([{"id": it.id, "model": it.model, "price": it.price} for it in items])

@app.post("/admin_api/prices")
@require_admin
def admin_prices_upsert():
    """
    JSON:
      - model, price
      - або prices: [{model, price}, ...]
    """
    data = request.get_json(force=True, silent=True) or {}
    batch = data.get("prices")
    changed = 0
    if isinstance(batch, list):
        for row in batch:
            model = str(row.get("model", "")).strip()
            if not model:
                continue
            price = int(row.get("price", 1))
            it = Price.query.filter_by(model=model).first()
            if it:
                it.price = price
            else:
                db.session.add(Price(model=model, price=price))
            changed += 1
        db.session.commit()
        log_action("prices_batch_upsert", str(changed))
        return jsonify(ok=True, changed=changed)
    model = str(data.get("model", "")).strip()
    if not model:
        return jsonify(ok=False, msg="model required"), 400
    price = int(data.get("price", 1))
    it = Price.query.filter_by(model=model).first()
    if it:
        it.price = price
        db.session.commit()
        log_action("price_update", model)
        return jsonify(ok=True, updated=True)
    db.session.add(Price(model=model, price=price))
    db.session.commit()
    log_action("price_add", model)
    return jsonify(ok=True, created=True)

# ---- Logs ----
@app.get("/admin_api/logs")
@require_admin
def admin_logs():
    items = ActivityLog.query.order_by(ActivityLog.id.desc()).limit(200).all()
    return jsonify([
        {"id": it.id, "action": it.action, "detail": it.detail, "created_at": it.created_at.isoformat()}
        for it in items
    ])


# =========================
# Run (local)
# =========================
if __name__ == "__main__":
    # Локально: flask dev server
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True)