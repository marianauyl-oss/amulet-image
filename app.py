# app.py
# -*- coding: utf-8 -*-
import os
import io
import csv
from datetime import datetime
from typing import Dict, Any, List

from flask import (
    Flask, jsonify, request, send_from_directory, abort
)
from flask_cors import CORS
from werkzeug.security import safe_str_cmp
from sqlalchemy import text, inspect, func

# Моделі — винесені в models.py
from models import db, License, ApiKey, Config, Price, ActivityLog

# =========================
# ========== APP ==========
# =========================
def _normalize_db_url(raw: str) -> str:
    if not raw:
        return "sqlite:///local.sqlite3"
    u = raw.strip()
    # Render/Heroku інколи дають postgres:// — міняємо на сучасний драйвер psycopg
    if u.startswith("postgres://"):
        u = "postgresql+psycopg://" + u[len("postgres://"):]
    elif u.startswith("postgresql://") and "+psycopg" not in u:
        u = "postgresql+psycopg://" + u[len("postgresql://"):]
    return u

app = Flask(__name__, static_folder="static", static_url_path="/")
CORS(app)

app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "change-me")
app.config["SQLALCHEMY_DATABASE_URI"] = _normalize_db_url(os.getenv("DATABASE_URL", "sqlite:///local.sqlite3"))
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# важливо: ініціалізуємо db через models.db
db.init_app(app)

ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASS", "admin")

# Моделі та ціни за замовчуванням
DEFAULT_PRICES: Dict[str, int] = {
    "seedream-v4": 1,
    "flux-dev": 1,
    "flux-pro-v1-1": 2,
    "gemini-2.5-flash": 1,
    "imagen3": 2,
    "classic-fast": 1,
}

# =========================
# ======= UTIL/AUTH =======
# =========================
def require_admin(fn):
    from functools import wraps
    @wraps(fn)
    def wrapper(*args, **kwargs):
        auth = request.authorization
        if not auth or not safe_str_cmp(auth.username or "", ADMIN_USER) or not safe_str_cmp(auth.password or "", ADMIN_PASS):
            return (
                jsonify({"ok": False, "msg": "Unauthorized"}),
                401,
                {"WWW-Authenticate": 'Basic realm="Admin"'},
            )
        return fn(*args, **kwargs)
    return wrapper

def log(action: str, details: str = ""):
    try:
        db.session.add(ActivityLog(action=action, details=details))
        db.session.commit()
    except Exception:
        db.session.rollback()

# =========================
# === SCHEMA ENSURERS  ====
# =========================
def _ensure_pg_defaults_and_columns():
    """
    Латаємо відсутні колонки/дефолти у вже існуючих таблицях PostgreSQL.
    Важливо: додаємо/виправляємо updated_at для config та price (NOT NULL + DEFAULT now()).
    """
    eng = db.engine
    if eng.dialect.name != "postgresql":
        return

    insp = inspect(eng)

    def has_table(tn: str) -> bool:
        try:
            return insp.has_table(tn)
        except Exception:
            return False

    with eng.begin() as conn:
        # ----- config.updated_at -----
        if has_table("config"):
            cols = {c["name"] for c in insp.get_columns("config")}
            if "updated_at" not in cols:
                conn.execute(text("ALTER TABLE config ADD COLUMN updated_at TIMESTAMPTZ"))
                conn.execute(text("UPDATE config SET updated_at = NOW() WHERE updated_at IS NULL"))
                conn.execute(text("ALTER TABLE config ALTER COLUMN updated_at SET DEFAULT NOW()"))
                conn.execute(text("ALTER TABLE config ALTER COLUMN updated_at SET NOT NULL"))
            else:
                # гарантуємо default + not null
                conn.execute(text("ALTER TABLE config ALTER COLUMN updated_at SET DEFAULT NOW()"))
                conn.execute(text("UPDATE config SET updated_at = NOW() WHERE updated_at IS NULL"))
                conn.execute(text("ALTER TABLE config ALTER COLUMN updated_at SET NOT NULL"))

        # ----- price.updated_at -----
        if has_table("price"):
            cols = {c["name"] for c in insp.get_columns("price")}
            if "updated_at" not in cols:
                conn.execute(text("ALTER TABLE price ADD COLUMN updated_at TIMESTAMPTZ"))
                conn.execute(text("UPDATE price SET updated_at = NOW() WHERE updated_at IS NULL"))
                conn.execute(text("ALTER TABLE price ALTER COLUMN updated_at SET DEFAULT NOW()"))
                conn.execute(text("ALTER TABLE price ALTER COLUMN updated_at SET NOT NULL"))
            else:
                conn.execute(text("ALTER TABLE price ALTER COLUMN updated_at SET DEFAULT NOW()"))
                conn.execute(text("UPDATE price SET updated_at = NOW() WHERE updated_at IS NULL"))
                conn.execute(text("ALTER TABLE price ALTER COLUMN updated_at SET NOT NULL"))

        # ----- apikey.in_use (BOOLEAN DEFAULT false) -----
        if has_table("apikey"):
            cols = {c["name"] for c in insp.get_columns("apikey")}
            if "in_use" not in cols:
                conn.execute(text("ALTER TABLE apikey ADD COLUMN in_use BOOLEAN DEFAULT FALSE"))
                conn.execute(text("UPDATE apikey SET in_use = FALSE WHERE in_use IS NULL"))

        # ----- license.status (VARCHAR DEFAULT 'active') -----
        if has_table("license"):
            cols = {c["name"] for c in insp.get_columns("license")}
            if "status" not in cols:
                conn.execute(text("ALTER TABLE license ADD COLUMN status VARCHAR(50) DEFAULT 'active'"))
                conn.execute(text("UPDATE license SET status='active' WHERE status IS NULL"))

def _ensure_base_schema_and_seed():
    """
    Створюємо таблиці, патчимо колонки, засіваємо початкові дані (config + prices).
    """
    db.create_all()  # створює відсутні таблиці із server_default для нових інстансів
    _ensure_pg_defaults_and_columns()

    # ---- seed Config (єдиний запис) ----
    if not Config.query.first():
        cfg = Config(
            latest_version=os.getenv("LATEST_VERSION", "2.3.3"),
            force_update=False,
            maintenance=False,
            maintenance_message="",
            update_links="[]",
            update_description="",
            updated_at=func.now(),
        )
        db.session.add(cfg)
        db.session.commit()

    # ---- seed Prices (без падіння на updated_at) ----
    existing = {p.model: p for p in Price.query.all()}
    changed = False
    for model, price in DEFAULT_PRICES.items():
        if model in existing:
            if existing[model].price != price:
                existing[model].price = price
                existing[model].updated_at = func.now()
                changed = True
        else:
            db.session.add(Price(model=model, price=price, updated_at=func.now()))
            changed = True
    if changed:
        db.session.commit()

# Запускаємо ініціалізацію при старті
with app.app_context():
    _ensure_base_schema_and_seed()

# =========================
# ====== STATIC/ADMIN =====
# =========================
@app.get("/")
def root():
    return send_from_directory(app.static_folder, "admin.html")

@app.get("/admin")
def admin_page():
    return send_from_directory(app.static_folder, "admin.html")

@app.get("/admin.css")
def admin_css():
    return send_from_directory(app.static_folder, "admin.css")

@app.get("/admin.js")
def admin_js():
    return send_from_directory(app.static_folder, "admin.js")

# =========================
# ======= HEALTH ==========
# =========================
@app.get("/healthz")
def healthz():
    try:
        db.session.execute(text("SELECT 1"))
        return jsonify({"ok": True, "db": "ok", "time": datetime.utcnow().isoformat()})
    except Exception as e:
        return jsonify({"ok": False, "db": str(e)}), 500

# =========================
# ======= ADMIN API =======
# =========================
@app.get("/admin_api/login")
@require_admin
def admin_login():
    return jsonify({"ok": True, "user": ADMIN_USER})

# ---- Licenses ----
@app.get("/admin_api/licenses")
@require_admin
def admin_licenses_list():
    q = License.query
    status = (request.args.get("status") or "").strip().lower()
    if status:
        q = q.filter(License.status == status)
    key_like = (request.args.get("q") or "").strip()
    if key_like:
        q = q.filter(License.key.ilike(f"%{key_like}%"))
    items = [x.to_dict() for x in q.order_by(License.id.desc()).all()]
    return jsonify({"ok": True, "items": items})

@app.post("/admin_api/licenses")
@require_admin
def admin_license_create():
    data = request.get_json(force=True, silent=True) or {}
    key = (data.get("key") or "").strip()
    credit = int(data.get("credit") or 0)
    status = (data.get("status") or "active").strip().lower()
    if not key:
        return jsonify({"ok": False, "msg": "key is required"}), 400
    if License.query.filter_by(key=key).first():
        return jsonify({"ok": False, "msg": "key exists"}), 409
    lic = License(key=key, credit=credit, status=status, last_active=None)
    db.session.add(lic)
    db.session.commit()
    log("license_create", f"{key} ({credit})")
    return jsonify({"ok": True, "item": lic.to_dict()})

@app.patch("/admin_api/licenses/<int:lic_id>")
@require_admin
def admin_license_update(lic_id: int):
    lic = License.query.get_or_404(lic_id)
    data = request.get_json(force=True, silent=True) or {}
    if "credit" in data:
        try:
            lic.credit = int(data["credit"])
        except Exception:
            return jsonify({"ok": False, "msg": "credit must be int"}), 400
    if "status" in data:
        lic.status = str(data["status"]).strip().lower() or lic.status
    if "mac_id" in data:
        lic.mac_id = (data["mac_id"] or "").strip() or None
    lic.last_active = datetime.utcnow()
    db.session.commit()
    log("license_update", f"{lic.key}")
    return jsonify({"ok": True, "item": lic.to_dict()})

@app.delete("/admin_api/licenses/<int:lic_id>")
@require_admin
def admin_license_delete(lic_id: int):
    lic = License.query.get_or_404(lic_id)
    key = lic.key
    db.session.delete(lic)
    db.session.commit()
    log("license_delete", key)
    return jsonify({"ok": True})

# ---- API Keys ----
@app.get("/admin_api/apikeys")
@require_admin
def admin_apikeys_list():
    q = ApiKey.query
    status = (request.args.get("status") or "").strip().lower()
    if status:
        q = q.filter(ApiKey.status == status)
    items = [x.to_dict() for x in q.order_by(ApiKey.id.desc()).all()]
    return jsonify({"ok": True, "items": items})

@app.post("/admin_api/apikeys")
@require_admin
def admin_apikeys_create_or_import():
    """
    Підтримує:
    1) JSON {api_key, status?, note?}
    2) multipart/form-data з файлом 'file' (txt: кожен ключ з нового рядка)
    3) raw text у полі 'text' (кожен рядок — ключ)
    """
    if request.files.get("file"):
        file = request.files["file"]
        content = file.read().decode("utf-8", errors="ignore")
        lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
        added, skipped = 0, 0
        for k in lines:
            if ApiKey.query.filter_by(api_key=k).first():
                skipped += 1
                continue
            db.session.add(ApiKey(api_key=k, status="active", in_use=False, note=None, updated_at=func.now()))
            added += 1
        db.session.commit()
        log("apikey_import", f"added={added}, skipped={skipped}")
        return jsonify({"ok": True, "added": added, "skipped": skipped})

    data = request.get_json(silent=True) or {}
    if isinstance(data, dict) and (data.get("text")):
        content = str(data["text"])
        lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
        added, skipped = 0, 0
        for k in lines:
            if ApiKey.query.filter_by(api_key=k).first():
                skipped += 1
                continue
            db.session.add(ApiKey(api_key=k, status="active", in_use=False, note=None, updated_at=func.now()))
            added += 1
        db.session.commit()
        log("apikey_import", f"added={added}, skipped={skipped}")
        return jsonify({"ok": True, "added": added, "skipped": skipped})

    api_key = (data.get("api_key") or "").strip()
    if not api_key:
        return jsonify({"ok": False, "msg": "api_key is required"}), 400
    if ApiKey.query.filter_by(api_key=api_key).first():
        return jsonify({"ok": False, "msg": "api_key exists"}), 409
    ak = ApiKey(api_key=api_key, status=str(data.get("status") or "active"), note=(data.get("note") or None))
    db.session.add(ak)
    db.session.commit()
    log("apikey_create", f"{ak.id}")
    return jsonify({"ok": True, "item": ak.to_dict()})

@app.patch("/admin_api/apikeys/<int:ak_id>")
@require_admin
def admin_apikey_update(ak_id: int):
    ak = ApiKey.query.get_or_404(ak_id)
    data = request.get_json(force=True, silent=True) or {}
    if "status" in data:
        ak.status = str(data["status"]).strip().lower() or ak.status
    if "in_use" in data:
        ak.in_use = bool(data["in_use"])
    if "note" in data:
        ak.note = (data["note"] or None)
    ak.updated_at = func.now()
    db.session.commit()
    log("apikey_update", f"{ak_id}")
    return jsonify({"ok": True, "item": ak.to_dict()})

@app.delete("/admin_api/apikeys/<int:ak_id>")
@require_admin
def admin_apikey_delete(ak_id: int):
    ak = ApiKey.query.get_or_404(ak_id)
    db.session.delete(ak)
    db.session.commit()
    log("apikey_delete", f"{ak_id}")
    return jsonify({"ok": True})

# ---- Config ----
@app.get("/admin_api/config")
@require_admin
def admin_get_config():
    c = Config.query.first()
    return jsonify({"ok": True, "item": c.to_dict() if c else None})

@app.post("/admin_api/config")
@require_admin
def admin_set_config():
    data = request.get_json(force=True, silent=True) or {}
    c = Config.query.first()
    if not c:
        c = Config()
        db.session.add(c)
    if "latest_version" in data:
        c.latest_version = str(data["latest_version"])
    if "force_update" in data:
        c.force_update = bool(data["force_update"])
    if "maintenance" in data:
        c.maintenance = bool(data["maintenance"])
    if "maintenance_message" in data:
        c.maintenance_message = str(data["maintenance_message"] or "")
    if "update_links" in data:
        # зберігаємо JSON-рядком
        import json
        if isinstance(data["update_links"], list):
            c.update_links = json.dumps(data["update_links"], ensure_ascii=False)
        else:
            c.update_links = str(data["update_links"] or "[]")
    if "update_description" in data:
        c.update_description = str(data["update_description"] or "")
    c.updated_at = func.now()
    db.session.commit()
    log("config_update", "")
    return jsonify({"ok": True, "item": c.to_dict()})

# ---- Prices ----
@app.get("/admin_api/prices")
@require_admin
def admin_prices_list():
    items = [p.to_dict() for p in Price.query.order_by(Price.model.asc()).all()]
    return jsonify({"ok": True, "items": items})

@app.post("/admin_api/prices")
@require_admin
def admin_prices_upsert():
    """
    Приймає:
      - JSON { model: "...", price: 2 }
      - або масив [{model, price}, ...]
    """
    payload = request.get_json(force=True, silent=True) or {}
    updates: List[Dict[str, Any]] = []
    if isinstance(payload, list):
        updates = payload
    elif isinstance(payload, dict) and "model" in payload:
        updates = [payload]
    else:
        return jsonify({"ok": False, "msg": "Invalid payload"}), 400

    changed = 0
    for it in updates:
        model = str(it.get("model") or "").strip()
        try:
            price = int(it.get("price"))
        except Exception:
            return jsonify({"ok": False, "msg": f"Bad price for model {model}"}), 400
        if not model or price <= 0:
            return jsonify({"ok": False, "msg": f"Invalid model or price: {model}"}), 400
        rec = Price.query.filter_by(model=model).first()
        if rec:
            rec.price = price
            rec.updated_at = func.now()
        else:
            db.session.add(Price(model=model, price=price, updated_at=func.now()))
        changed += 1
    db.session.commit()
    log("prices_upsert", f"{changed} items")
    return jsonify({"ok": True, "changed": changed})

# ---- Logs ----
@app.get("/admin_api/logs")
@require_admin
def admin_logs():
    n = int(request.args.get("limit") or 100)
    items = [x.to_dict() for x in ActivityLog.query.order_by(ActivityLog.id.desc()).limit(n).all()]
    return jsonify({"ok": True, "items": items})

# =========================
# === PUBLIC (client)  ====
# =========================
@app.post("/api/get_prices")
def public_get_prices():
    """Повертає карту цін (для десктоп-клієнта Seedream)."""
    items = Price.query.all()
    return jsonify({"ok": True, "prices": {p.model: p.price for p in items}})

@app.get("/api/get_config")
def public_get_config():
    c = Config.query.first()
    if not c:
        return jsonify({"ok": False, "msg": "no config"}), 404
    import json
    try:
        links = json.loads(c.update_links or "[]")
    except Exception:
        links = []
    return jsonify({
        "ok": True,
        "config": {
            "latest_version": c.latest_version,
            "force_update": bool(c.force_update),
            "maintenance": bool(c.maintenance),
            "maintenance_message": c.maintenance_message or "",
            "update_links": links,
            "update_description": c.update_description or "",
        }
    })

# =========================
# ======= ERROR JSON ======
# =========================
@app.errorhandler(404)
def _404(_e):
    # для API — JSON, для статичних шляхів — віддаємо admin.html
    if request.path.startswith("/admin_api") or request.path.startswith("/api"):
        return jsonify({"ok": False, "msg": "Not found"}), 404
    return send_from_directory(app.static_folder, "admin.html")

@app.errorhandler(500)
def _500(e):
    try:
        db.session.rollback()
    except Exception:
        pass
    return jsonify({"ok": False, "msg": "Internal server error"}), 500

# =========================
# ======== RUN DEV ========
# =========================
if __name__ == "__main__":
    # Локально: python app.py
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True)