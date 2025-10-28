# app.py
# -*- coding: utf-8 -*-
import os
import base64
from datetime import datetime, timezone
from hmac import compare_digest

from flask import (
    Flask, request, jsonify, Response, send_from_directory, send_file
)
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from sqlalchemy import text, inspect

# ======== Flask / DB ========
app = Flask(__name__, static_url_path="", static_folder="static")

CORS(app, resources={r"/*": {"origins": "*"}})

# DATABASE_URL: приклад:
# postgresql://amulet_db_user:...@dpg-xxx/amulet_db
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
    "DATABASE_URL",
    "sqlite:///amulet.db"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["JSON_AS_ASCII"] = False

# Якщо моделі окремо — імпортуємо
from models import db, License, ApiKey, Config, Price, ActivityLog  # noqa: E402

db.init_app(app)

# ======== Адмін креденшли ========
ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASS", "admin")

def _basic_auth_ok(req) -> bool:
    auth = req.headers.get("Authorization", "")
    if not auth.startswith("Basic "):
        return False
    try:
        raw = base64.b64decode(auth.split(" ", 1)[1]).decode("utf-8", "ignore")
        username, password = raw.split(":", 1)
    except Exception:
        return False
    return (
        compare_digest(str(username or ""), str(ADMIN_USER or "")) and
        compare_digest(str(password or ""), str(ADMIN_PASS or ""))
    )

def _require_admin():
    if not _basic_auth_ok(request):
        return Response("Unauthorized", 401, {"WWW-Authenticate": 'Basic realm="admin"'})
    return None

# ======== Авто-міграції (легкі) ========
def _ensure_columns_exist():
    """Додає прості колонки в існуючих таблицях, якщо їх нема (PostgreSQL)."""
    eng = db.engine
    insp = inspect(eng)

    def has_table(tname: str) -> bool:
        try:
            insp.get_columns(tname)
            return True
        except Exception:
            return False

    def ensure(table: str, colname: str, ddl_sql: str):
        if not has_table(table):
            return
        cols = {c["name"] for c in insp.get_columns(table)}
        if colname not in cols:
            with eng.connect() as con:
                con.execute(text(f"ALTER TABLE {table} ADD COLUMN {ddl_sql};"))
                con.commit()

    # config.updated_at
    ensure("config", "updated_at", "updated_at TIMESTAMPTZ DEFAULT now()")
    # price.updated_at
    ensure("price", "updated_at", "updated_at TIMESTAMPTZ DEFAULT now()")
    # api_key.in_use / api_key.note (на випадок відсутності)
    ensure("api_key", "in_use", "in_use BOOLEAN DEFAULT FALSE")
    ensure("api_key", "note", "note TEXT")
    # license.last_active (якщо раптом нема)
    ensure("license", "last_active", "last_active TIMESTAMPTZ")

def _ensure_base_schema():
    """create_all + первинна ініціалізація config та price"""
    db.create_all()

    # гарантія наявності колонок
    _ensure_columns_exist()

    # CONFIG (єдиний рядок)
    if not Config.query.first():
        cfg = Config(
            latest_version="2.3.3",
            force_update=False,
            maintenance=False,
            maintenance_message="",
            update_links="[]",
            update_description="",
            updated_at=datetime.now(timezone.utc),
        )
        db.session.add(cfg)

    # PRICES (якщо порожньо — піднімаємо дефолт)
    if Price.query.count() == 0:
        defaults = {
            "seedream-v4": 1,
            "flux-dev": 1,
            "flux-pro-v1-1": 2,
            "gemini-2.5-flash": 1,
            "imagen3": 2,
            "classic-fast": 1,
        }
        for model_id, val in defaults.items():
            db.session.add(Price(
                model=model_id,
                price=int(val),
                updated_at=datetime.now(timezone.utc),
            ))
    db.session.commit()

with app.app_context():
    _ensure_base_schema()

# ======== Сервінг адмінки ========
@app.get("/")
def root():
    return send_from_directory("static", "admin.html")

@app.get("/admin")
def admin_html():
    return send_from_directory("static", "admin.html")

@app.get("/admin.js")
def admin_js():
    return send_from_directory("static", "admin.js")

@app.get("/admin.css")
def admin_css():
    return send_from_directory("static", "admin.css")

@app.get("/healthz")
def healthz():
    return jsonify(ok=True, time=datetime.utcnow().isoformat() + "Z")

# ======== ADMIN API ========
@app.get("/admin_api/login")
def admin_login():
    unauth = _require_admin()
    if unauth:
        return unauth
    return jsonify(ok=True)

# ---- Licenses
@app.get("/admin_api/licenses")
def admin_list_licenses():
    unauth = _require_admin();  # noqa: E702
    if unauth: return unauth    # noqa: E701
    qs = License.query.order_by(License.id.desc()).all()
    out = []
    for x in qs:
        out.append({
            "id": x.id,
            "key": x.key,
            "mac_id": x.mac_id,
            "status": x.status,
            "credit": x.credit,
            "last_active": x.last_active.isoformat() if x.last_active else None
        })
    return jsonify(ok=True, items=out)

@app.post("/admin_api/licenses")
def admin_add_license():
    unauth = _require_admin()
    if unauth:
        return unauth
    j = request.json or {}
    key = str(j.get("key", "")).strip()
    credit = int(j.get("credit", 0))
    status = str(j.get("status", "active")).strip().lower()
    if not key:
        return jsonify(ok=False, msg="Key required"), 400
    if License.query.filter_by(key=key).first():
        return jsonify(ok=False, msg="Key exists"), 400
    lic = License(key=key, credit=credit, status=status, last_active=None)
    db.session.add(lic); db.session.commit()
    return jsonify(ok=True, id=lic.id)

@app.delete("/admin_api/licenses/<int:lic_id>")
def admin_del_license(lic_id):
    unauth = _require_admin()
    if unauth:
        return unauth
    row = License.query.get(lic_id)
    if not row:
        return jsonify(ok=False, msg="Not found"), 404
    db.session.delete(row); db.session.commit()
    return jsonify(ok=True)

# ---- API Keys
@app.get("/admin_api/apikeys")
def admin_list_apikeys():
    unauth = _require_admin()
    if unauth:
        return unauth
    qs = ApiKey.query.order_by(ApiKey.id.desc()).all()
    out = []
    for x in qs:
        out.append({
            "id": x.id,
            "api_key": x.api_key,
            "status": x.status,
            "in_use": bool(x.in_use),
            "last_used": x.last_used.isoformat() if x.last_used else None,
            "note": x.note or ""
        })
    return jsonify(ok=True, items=out)

@app.post("/admin_api/apikeys")
def admin_add_apikey():
    unauth = _require_admin()
    if unauth:
        return unauth
    j = request.json or {}
    api_key = str(j.get("api_key", "")).strip()
    status = str(j.get("status", "active")).strip().lower()
    note = str(j.get("note", "")).strip()
    if not api_key:
        return jsonify(ok=False, msg="api_key required"), 400
    if ApiKey.query.filter_by(api_key=api_key).first():
        return jsonify(ok=False, msg="Duplicate key"), 400
    row = ApiKey(api_key=api_key, status=status, in_use=False, note=note, last_used=None)
    db.session.add(row); db.session.commit()
    return jsonify(ok=True, id=row.id)

@app.post("/admin_api/apikeys/<int:pk>/toggle_use")
def admin_toggle_api_use(pk):
    unauth = _require_admin()
    if unauth:
        return unauth
    row = ApiKey.query.get(pk)
    if not row:
        return jsonify(ok=False, msg="Not found"), 404
    row.in_use = not bool(row.in_use)
    row.last_used = datetime.now(timezone.utc)
    db.session.commit()
    return jsonify(ok=True, in_use=bool(row.in_use))

@app.delete("/admin_api/apikeys/<int:pk>")
def admin_delete_apikey(pk):
    unauth = _require_admin()
    if unauth:
        return unauth
    row = ApiKey.query.get(pk)
    if not row:
        return jsonify(ok=False, msg="Not found"), 404
    db.session.delete(row); db.session.commit()
    return jsonify(ok=True)

# ---- Config
@app.get("/admin_api/config")
def admin_get_config():
    unauth = _require_admin()
    if unauth:
        return unauth
    cfg = Config.query.first()
    if not cfg:
        cfg = Config(
            latest_version="2.3.3",
            force_update=False,
            maintenance=False,
            maintenance_message="",
            update_links="[]",
            update_description="",
            updated_at=datetime.now(timezone.utc),
        )
        db.session.add(cfg); db.session.commit()
    return jsonify(ok=True, config={
        "latest_version": cfg.latest_version,
        "force_update": bool(cfg.force_update),
        "maintenance": bool(cfg.maintenance),
        "maintenance_message": cfg.maintenance_message or "",
        "update_links": cfg.update_links or "[]",
        "update_description": cfg.update_description or "",
        "updated_at": cfg.updated_at.isoformat() if cfg.updated_at else None
    })

@app.post("/admin_api/config")
def admin_set_config():
    unauth = _require_admin()
    if unauth:
        return unauth
    j = request.json or {}
    cfg = Config.query.first()
    if not cfg:
        cfg = Config()
        db.session.add(cfg)
    cfg.latest_version = str(j.get("latest_version", cfg.latest_version or "2.3.3"))
    cfg.force_update = bool(j.get("force_update", cfg.force_update or False))
    cfg.maintenance = bool(j.get("maintenance", cfg.maintenance or False))
    cfg.maintenance_message = str(j.get("maintenance_message", cfg.maintenance_message or ""))
    # приймаємо або JSON-рядок, або масив — зберігаємо як JSON-рядок
    links = j.get("update_links", cfg.update_links or "[]")
    if isinstance(links, list):
        import json as _json
        links = _json.dumps(links, ensure_ascii=False)
    cfg.update_links = str(links)
    cfg.update_description = str(j.get("update_description", cfg.update_description or ""))
    cfg.updated_at = datetime.now(timezone.utc)
    db.session.commit()
    return jsonify(ok=True)

# ---- Prices
@app.get("/admin_api/prices")
def admin_get_prices():
    unauth = _require_admin()
    if unauth:
        return unauth
    items = Price.query.order_by(Price.id.asc()).all()
    out = [{"id": p.id, "model": p.model, "price": p.price,
            "updated_at": p.updated_at.isoformat() if p.updated_at else None} for p in items]
    return jsonify(ok=True, items=out)

@app.post("/admin_api/prices")
def admin_set_price():
    unauth = _require_admin()
    if unauth:
        return unauth
    j = request.json or {}
    model_id = str(j.get("model", "")).strip()
    price_val = int(j.get("price", 0))
    if not model_id or price_val <= 0:
        return jsonify(ok=False, msg="Invalid model/price"), 400
    row = Price.query.filter_by(model=model_id).first()
    if row:
        row.price = price_val
        row.updated_at = datetime.now(timezone.utc)
    else:
        row = Price(model=model_id, price=price_val, updated_at=datetime.now(timezone.utc))
        db.session.add(row)
    db.session.commit()
    return jsonify(ok=True, id=row.id)

# ---- Logs (read-only)
@app.get("/admin_api/logs")
def admin_get_logs():
    unauth = _require_admin()
    if unauth:
        return unauth
    limit = int(request.args.get("limit", 200))
    qs = ActivityLog.query.order_by(ActivityLog.id.desc()).limit(limit).all()
    out = []
    for x in qs:
        out.append({
            "id": x.id,
            "action": x.action,
            "details": x.details,
            "created_at": x.created_at.isoformat() if x.created_at else None
        })
    return jsonify(ok=True, items=out)

# ======== CLIENT-FACING API (для десктопу) ========
def _get_prices_map():
    rows = Price.query.all()
    if not rows:
        # fallback у разі пустої таблиці
        return {
            "seedream-v4": 1,
            "flux-dev": 1,
            "flux-pro-v1-1": 2,
            "gemini-2.5-flash": 1,
            "imagen3": 2,
            "classic-fast": 1,
        }
    return {r.model: int(r.price) for r in rows}

@app.post("/license/check")
def license_check():
    j = request.json or {}
    key = str(j.get("key", "")).strip()
    mac = str(j.get("mac", "")).strip().upper()
    if not key or not mac:
        return jsonify(ok=False, msg="Missing key or mac"), 400
    row = License.query.filter_by(key=key).first()
    if not row:
        return jsonify(ok=False, msg="Key not found")
    if (row.status or "").lower() != "active":
        return jsonify(ok=False, msg="Inactive key", status=row.status or "unknown")
    if not row.mac_id:
        row.mac_id = mac
    elif row.mac_id.upper().strip() != mac:
        return jsonify(ok=False, msg="Already used on another device", status="active")
    row.last_active = datetime.now(timezone.utc)
    db.session.commit()
    return jsonify(ok=True, credit=int(row.credit), status="active")

@app.post("/license/debit")
def license_debit():
    j = request.json or {}
    key = str(j.get("key", "")).strip()
    mac = str(j.get("mac", "")).strip().upper()
    model = str(j.get("model", "")).strip()
    count = int(j.get("count", 0))
    if not key or not mac or not model or count <= 0:
        return jsonify(ok=False, msg="Invalid payload"), 400

    row = License.query.filter_by(key=key).first()
    if not row:
        return jsonify(ok=False, msg="Key not found")
    if (row.status or "").lower() != "active":
        return jsonify(ok=False, msg="Inactive key", status=row.status or "unknown")
    if not row.mac_id:
        row.mac_id = mac
    elif row.mac_id.upper().strip() != mac:
        return jsonify(ok=False, msg="Key bound to another device", status="active")

    prices = _get_prices_map()
    unit = int(prices.get(model, 1))
    total_cost = unit * count
    if int(row.credit) < total_cost:
        return jsonify(ok=False, msg="Insufficient credit", credit=int(row.credit))
    row.credit = int(row.credit) - total_cost
    row.last_active = datetime.now(timezone.utc)
    db.session.commit()
    return jsonify(ok=True, credit=int(row.credit), debited=total_cost, unitPrice=unit, model=model, count=count)

@app.post("/next_api_key")
def next_api_key():
    # шукаємо перший active & not in_use
    row = ApiKey.query.filter_by(status="active", in_use=False).order_by(ApiKey.id.asc()).first()
    if not row:
        return jsonify(ok=False, msg="No ACTIVE free API keys")
    row.in_use = True
    row.last_used = datetime.now(timezone.utc)
    db.session.commit()
    return jsonify(ok=True, api_key=row.api_key)

@app.post("/release_api_key")
def release_api_key():
    j = request.json or {}
    api_key = str(j.get("api_key", "")).strip()
    if not api_key:
        return jsonify(ok=False, msg="Missing api_key"), 400
    row = ApiKey.query.filter_by(api_key=api_key).first()
    if not row:
        return jsonify(ok=False, msg="API key not found")
    row.in_use = False
    row.last_used = datetime.now(timezone.utc)
    db.session.commit()
    return jsonify(ok=True, status=row.status, changed=True)

@app.post("/deactivate_api_key")
def deactivate_api_key():
    j = request.json or {}
    api_key = str(j.get("api_key", "")).strip()
    if not api_key:
        return jsonify(ok=False, msg="Missing api_key"), 400
    row = ApiKey.query.filter_by(api_key=api_key).first()
    if not row:
        return jsonify(ok=False, msg="API key not found")
    row.status = "inactive"
    row.in_use = False
    row.last_used = datetime.now(timezone.utc)
    db.session.commit()
    return jsonify(ok=True)

@app.post("/get_config")
def get_config():
    cfg = Config.query.first()
    if not cfg:
        cfg = Config(
            latest_version="2.3.3",
            force_update=False,
            maintenance=False,
            maintenance_message="",
            update_links="[]",
            update_description="",
            updated_at=datetime.now(timezone.utc),
        )
        db.session.add(cfg); db.session.commit()
    return jsonify(ok=True, config={
        "latest_version": cfg.latest_version,
        "force_update": bool(cfg.force_update),
        "maintenance": bool(cfg.maintenance),
        "maintenance_message": cfg.maintenance_message or "",
        "update_links": cfg.update_links or "[]",
        "update_description": cfg.update_description or "",
    })

@app.post("/get_prices")
def get_prices():
    return jsonify(ok=True, prices=_get_prices_map())

# ======== gunicorn entry ========
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")))