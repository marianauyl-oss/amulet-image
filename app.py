import os, re, json, base64, secrets
from datetime import datetime
from functools import wraps

from flask import (
    Flask, request, jsonify, send_from_directory, make_response
)
from flask_cors import CORS
from sqlalchemy import text, inspect, or_
from sqlalchemy.exc import IntegrityError

from models import db, License, ApiKey, Config, Price, ActivityLog, utcnow

# ---------- App / DB ----------
app = Flask(__name__, static_folder=None)
CORS(app, resources={r"/admin_api/*": {"origins": "*"}})

app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev_secret_change_me")
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if not DATABASE_URL:
    # SQLite за замовчуванням у файлі amulet.db в корені
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///amulet.db"
else:
    app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

DEFAULT_PRICES = {
    "seedream-v4": 1,
    "flux-dev": 1,
    "flux-pro-v1-1": 2,
    "gemini-2.5-flash": 1,
    "imagen3": 2,
    "classic-fast": 1,
}

# ---------- Auth ----------
ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASS", "admin123")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")  # альтернативний токен (заголовок X-Admin-Token або ?token=)

def _basic_auth_ok():
    # токен
    tok = request.headers.get("X-Admin-Token") or request.args.get("token")
    if ADMIN_TOKEN and tok and secrets.compare_digest(tok, ADMIN_TOKEN):
        return True

    # Basic
    auth = request.authorization
    if not auth:
        return False
    return secrets.compare_digest(auth.username or "", ADMIN_USER) and \
           secrets.compare_digest(auth.password or "", ADMIN_PASS)

def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if _basic_auth_ok():
            return fn(*args, **kwargs)
        resp = make_response("Auth required", 401)
        resp.headers["WWW-Authenticate"] = 'Basic realm="Amulet Admin"'
        return resp
    return wrapper

# ---------- Helpers ----------
def fmt_dt(dt):
    if not dt: return ""
    if isinstance(dt, str): return dt
    return dt.strftime("%Y-%m-%d %H:%M:%S")

def log_event(event, meta=None):
    try:
        db.session.add(ActivityLog(event=event, meta=json.dumps(meta or {}, ensure_ascii=False)))
        db.session.commit()
    except Exception:
        db.session.rollback()

def paginate(query, page, page_size):
    total = query.count()
    pages = max(1, (total + page_size - 1) // page_size)
    items = query.offset((page-1)*page_size).limit(page_size).all()
    return total, pages, items

def ensure_schema():
    """Створює таблиці та додає відсутні колонки (для старих SQLite)."""
    with app.app_context():
        db.create_all()

        insp = inspect(db.engine)

        def add_col_if_missing(table, coldef_sql):
            # SQLite/PG: проста перевірка — якщо колонки нема, додаємо
            cols = {c["name"] for c in insp.get_columns(table)}
            name = coldef_sql.split()[0].strip('"').strip()
            if name not in cols:
                with db.engine.begin() as conn:
                    conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN {coldef_sql}'))

        # license
        if insp.has_table("license"):
            add_col_if_missing("license", '"mac_id" VARCHAR(64)')
            add_col_if_missing("license", '"status" VARCHAR(32) DEFAULT \'active\'')
            add_col_if_missing("license", '"credit" INTEGER DEFAULT 0')
            add_col_if_missing("license", '"last_active" TIMESTAMP')

        # apikey
        if insp.has_table("apikey"):
            add_col_if_missing("apikey", '"status" VARCHAR(16) DEFAULT \'active\'')
            # boolean як INTEGER для sqlite сумісності
            add_col_if_missing("apikey", '"in_use" BOOLEAN DEFAULT 0')
            add_col_if_missing("apikey", '"last_used" TIMESTAMP')
            add_col_if_missing("apikey", '"note" VARCHAR(255)')

        # config
        if insp.has_table("config"):
            add_col_if_missing("config", '"latest_version" VARCHAR(32) DEFAULT \'2.3.3\'')
            add_col_if_missing("config", '"force_update" BOOLEAN DEFAULT 0')
            add_col_if_missing("config", '"maintenance" BOOLEAN DEFAULT 0')
            add_col_if_missing("config", '"maintenance_message" VARCHAR(500) DEFAULT \'\'')
            add_col_if_missing("config", '"update_description" TEXT DEFAULT \'\'')
            add_col_if_missing("config", '"update_links" TEXT DEFAULT \'[]\'')
            add_col_if_missing("config", '"updated_at" TIMESTAMP')

        # price
        if insp.has_table("price"):
            add_col_if_missing("price", '"model" VARCHAR(80)')
            add_col_if_missing("price", '"price" INTEGER')

        # ініціалізація config
        if db.session.query(Config).count() == 0:
            cfg = Config(
                latest_version="2.3.3",
                force_update=False,
                maintenance=False,
                maintenance_message="",
                update_description="",
                update_links="[]",
                updated_at=utcnow()
            )
            db.session.add(cfg)
            db.session.commit()

        # Якщо таблиця price порожня — заповнюємо дефолтами
        if db.session.query(Price).count() == 0:
            for m, p in DEFAULT_PRICES.items():
                db.session.add(Price(model=m, price=p))
            db.session.commit()

ensure_schema()

# ---------- Static (захищаємо, щоб спливла basic-auth) ----------
@app.route("/")
@admin_required
def root():
    # віддай admin.html зі статичної папки "static" (поклади туди свої admin.html/admin.js/admin.css)
    return send_from_directory("static", "admin.html")

@app.route("/admin.css")
@admin_required
def css():
    return send_from_directory("static", "admin.css")

@app.route("/admin.js")
@admin_required
def js():
    return send_from_directory("static", "admin.js")

# Health
@app.get("/healthz")
def health():
    return jsonify(ok=True, time=fmt_dt(datetime.utcnow()))

# ---------- Admin API ----------
@app.get("/admin_api/login")
@admin_required
def admin_login_ping():
    return jsonify(ok=True, user=ADMIN_USER)

# ---- Licenses ----
@app.get("/admin_api/licenses")
@admin_required
def admin_licenses():
    page = int(request.args.get("page", 1))
    page_size = min(100, int(request.args.get("page_size", 20)))
    q = (request.args.get("q") or "").strip()
    status = (request.args.get("status") or "").strip().lower()

    query = License.query
    if q:
        qs = f"%{q}%"
        query = query.filter(or_(License.key.ilike(qs),
                                 License.mac_id.ilike(qs)))
    if status:
        query = query.filter(License.status == status)

    query = query.order_by(License.id.desc())
    total, pages, items = paginate(query, page, page_size)
    data = []
    for it in items:
        data.append({
            "id": it.id,
            "key": it.key,
            "mac_id": it.mac_id,
            "status": it.status,
            "credit": it.credit,
            "last_active": fmt_dt(it.last_active),
            "created_at": fmt_dt(it.created_at),
            "updated_at": fmt_dt(it.updated_at),
        })
    return jsonify(ok=True, page=page, pages=pages, total=total, items=data)

@app.post("/admin_api/licenses")
@admin_required
def admin_license_create():
    body = request.get_json(force=True, silent=True) or {}
    key = (body.get("key") or "").strip()
    if not key:
        # простий генератор ключа XXXX-XXXX-XXXX
        import random, string
        def chunk():
            return "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
        key = f"{chunk()}-{chunk()}-{chunk()}"

    lic = License(
        key=key,
        mac_id=(body.get("mac_id") or "").strip() or None,
        status=(body.get("status") or "active").strip(),
        credit=int(body.get("credit") or 0)
    )
    db.session.add(lic)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify(ok=False, msg="Key already exists"), 400

    log_event("license.create", {"id": lic.id, "key": lic.key})
    return jsonify(ok=True, id=lic.id)

@app.put("/admin_api/licenses/<int:lic_id>")
@admin_required
def admin_license_update(lic_id):
    lic = License.query.get_or_404(lic_id)
    body = request.get_json(force=True, silent=True) or {}
    if "key" in body:
        newkey = (body.get("key") or "").strip()
        if newkey and newkey != lic.key:
            lic.key = newkey
    if "mac_id" in body:
        lic.mac_id = (body.get("mac_id") or "").strip() or None
    if "status" in body:
        lic.status = (body.get("status") or "active").strip()
    if "credit" in body:
        lic.credit = int(body.get("credit") or lic.credit)
    db.session.commit()
    log_event("license.update", {"id": lic.id})
    return jsonify(ok=True)

@app.delete("/admin_api/licenses/<int:lic_id>")
@admin_required
def admin_license_delete(lic_id):
    lic = License.query.get_or_404(lic_id)
    db.session.delete(lic)
    db.session.commit()
    log_event("license.delete", {"id": lic_id})
    return jsonify(ok=True)

@app.post("/admin_api/licenses/bulk")
@admin_required
def admin_license_bulk():
    """
    Приймає:
      - multipart/form-data з 'file' (txt: один ключ у рядку) і опц. 'status', 'credit'
      - або JSON: {"keys": ["AAA-BBB-CCC", ...], "status":"active", "credit":10}
    """
    created, skipped = 0, 0
    status = (request.form.get("status") or request.args.get("status") or "active").strip()
    credit = int(request.form.get("credit") or request.args.get("credit") or 0)

    keys = []
    if "file" in request.files:
        content = request.files["file"].read().decode("utf-8", errors="ignore")
        for line in content.splitlines():
            k = line.strip()
            if k:
                keys.append(k)
    else:
        body = request.get_json(force=True, silent=True) or {}
        keys = [str(x).strip() for x in body.get("keys", []) if str(x).strip()]
        credit = int(body.get("credit") or credit)
        status = (body.get("status") or status).strip() or "active"

    for k in keys:
        if not k: continue
        if db.session.query(License.id).filter_by(key=k).first():
            skipped += 1
            continue
        db.session.add(License(key=k, status=status, credit=credit))
        created += 1
    db.session.commit()
    log_event("license.bulk", {"created": created, "skipped": skipped})
    return jsonify(ok=True, created=created, skipped=skipped)

@app.post("/admin_api/licenses/<int:lic_id>/credit_adjust")
@admin_required
def admin_license_credit_adjust(lic_id):
    body = request.get_json(force=True, silent=True) or {}
    delta = int(body.get("delta") or 0)
    lic = License.query.get_or_404(lic_id)
    lic.credit = max(0, int(lic.credit) + delta)
    db.session.commit()
    log_event("license.credit_adjust", {"id": lic_id, "delta": delta})
    return jsonify(ok=True, credit=lic.credit)

# ---- API Keys ----
@app.get("/admin_api/apikeys")
@admin_required
def admin_apikeys():
    page = int(request.args.get("page", 1))
    page_size = min(100, int(request.args.get("page_size", 20)))
    q = (request.args.get("q") or "").strip()
    status = (request.args.get("status") or "").strip().lower()

    query = ApiKey.query
    if q:
        qs = f"%{q}%"
        query = query.filter(or_(ApiKey.api_key.ilike(qs),
                                 ApiKey.note.ilike(qs)))
    if status:
        query = query.filter(ApiKey.status == status)

    query = query.order_by(ApiKey.id.desc())
    total, pages, items = paginate(query, page, page_size)
    data = []
    for it in items:
        data.append({
            "id": it.id,
            "api_key": it.api_key,
            "status": it.status,
            "in_use": bool(it.in_use),
            "last_used": fmt_dt(it.last_used),
            "note": it.note or "",
            "created_at": fmt_dt(it.created_at),
            "updated_at": fmt_dt(it.updated_at),
        })
    return jsonify(ok=True, page=page, pages=pages, total=total, items=data)

@app.post("/admin_api/apikeys")
@admin_required
def admin_apikey_create():
    body = request.get_json(force=True, silent=True) or {}
    api_key = (body.get("api_key") or "").strip()
    if not api_key:
        return jsonify(ok=False, msg="api_key required"), 400
    ak = ApiKey(api_key=api_key,
                status=(body.get("status") or "active").strip(),
                note=(body.get("note") or "").strip() or None)
    db.session.add(ak)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify(ok=False, msg="api_key exists"), 400
    log_event("apikey.create", {"id": ak.id})
    return jsonify(ok=True, id=ak.id)

@app.put("/admin_api/apikeys/<int:key_id>")
@admin_required
def admin_apikey_update(key_id):
    ak = ApiKey.query.get_or_404(key_id)
    body = request.get_json(force=True, silent=True) or {}
    if "api_key" in body:
        v = (body.get("api_key") or "").strip()
        if v and v != ak.api_key:
            ak.api_key = v
    if "status" in body:
        ak.status = (body.get("status") or "active").strip()
    if "in_use" in body:
        ak.in_use = bool(body.get("in_use"))
    if "note" in body:
        ak.note = (body.get("note") or "").strip() or None
    db.session.commit()
    log_event("apikey.update", {"id": key_id})
    return jsonify(ok=True)

@app.delete("/admin_api/apikeys/<int:key_id>")
@admin_required
def admin_apikey_delete(key_id):
    ak = ApiKey.query.get_or_404(key_id)
    db.session.delete(ak)
    db.session.commit()
    log_event("apikey.delete", {"id": key_id})
    return jsonify(ok=True)

@app.post("/admin_api/apikeys/bulk")
@admin_required
def admin_apikey_bulk():
    """
    TXT: кожен ключ у новому рядку.
    Приймає multipart 'file' або JSON {"keys":[...], "status":"active"}
    """
    created, skipped = 0, 0
    status = (request.form.get("status") or request.args.get("status") or "active").strip()
    keys = []
    if "file" in request.files:
        content = request.files["file"].read().decode("utf-8", errors="ignore")
        for line in content.splitlines():
            v = line.strip()
            if v: keys.append(v)
    else:
        body = request.get_json(force=True, silent=True) or {}
        keys = [str(x).strip() for x in body.get("keys", []) if str(x).strip()]
        status = (body.get("status") or status).strip() or "active"

    for k in keys:
        if db.session.query(ApiKey.id).filter_by(api_key=k).first():
            skipped += 1
            continue
        db.session.add(ApiKey(api_key=k, status=status, in_use=False))
        created += 1
    db.session.commit()
    log_event("apikey.bulk", {"created": created, "skipped": skipped})
    return jsonify(ok=True, created=created, skipped=skipped)

# ---- Prices (Models) ----
@app.get("/admin_api/prices")
@admin_required
def admin_prices():
    page = int(request.args.get("page", 1))
    page_size = min(200, int(request.args.get("page_size", 50)))
    q = (request.args.get("q") or "").strip()
    query = Price.query
    if q:
        qs = f"%{q}%"
        query = query.filter(Price.model.ilike(qs))
    query = query.order_by(Price.model.asc())
    total, pages, items = paginate(query, page, page_size)
    data = [{"id": it.id, "model": it.model, "price": it.price,
             "created_at": fmt_dt(it.created_at), "updated_at": fmt_dt(it.updated_at)} for it in items]
    return jsonify(ok=True, page=page, pages=pages, total=total, items=data)

@app.post("/admin_api/prices")
@admin_required
def admin_price_upsert():
    body = request.get_json(force=True, silent=True) or {}
    model = (body.get("model") or "").strip()
    price = int(body.get("price") or 0)
    if not model or price <= 0:
        return jsonify(ok=False, msg="model and positive price required"), 400
    p = Price.query.filter_by(model=model).first()
    if p:
        p.price = price
    else:
        p = Price(model=model, price=price)
        db.session.add(p)
    db.session.commit()
    log_event("price.upsert", {"model": model, "price": price})
    return jsonify(ok=True, id=p.id, model=p.model, price=p.price)

@app.put("/admin_api/prices/<int:price_id>")
@admin_required
def admin_price_update(price_id):
    p = Price.query.get_or_404(price_id)
    body = request.get_json(force=True, silent=True) or {}
    if "model" in body:
        v = (body.get("model") or "").strip()
        if v and v != p.model:
            if db.session.query(Price.id).filter_by(model=v).first():
                return jsonify(ok=False, msg="model exists"), 400
            p.model = v
    if "price" in body:
        pv = int(body.get("price") or 0)
        if pv > 0:
            p.price = pv
    db.session.commit()
    log_event("price.update", {"id": p.id})
    return jsonify(ok=True)

@app.delete("/admin_api/prices/<int:price_id>")
@admin_required
def admin_price_delete(price_id):
    p = Price.query.get_or_404(price_id)
    db.session.delete(p)
    db.session.commit()
    log_event("price.delete", {"id": price_id})
    return jsonify(ok=True)

@app.post("/admin_api/prices/bulk")
@admin_required
def admin_price_bulk():
    """
    TXT: рядок формату model=price або model,price або 'model price'
    """
    created, updated, skipped = 0, 0, 0
    pairs = []
    if "file" in request.files:
        content = request.files["file"].read().decode("utf-8", errors="ignore")
        lines = content.splitlines()
    else:
        body = request.get_json(force=True, silent=True) or {}
        raw = body.get("data") or ""
        lines = str(raw).splitlines()

    for ln in lines:
        ln = ln.strip()
        if not ln: continue
        if "=" in ln:
            m, p = ln.split("=", 1)
        elif "," in ln:
            m, p = ln.split(",", 1)
        else:
            parts = ln.split()
            if len(parts) < 2:
                skipped += 1; continue
            m, p = parts[0], parts[1]
        model = m.strip()
        try:
            price = int(str(p).strip())
        except Exception:
            skipped += 1; continue
        if not model or price <= 0:
            skipped += 1; continue
        pairs.append((model, price))

    for model, price in pairs:
        obj = Price.query.filter_by(model=model).first()
        if obj:
            if obj.price != price:
                obj.price = price
                updated += 1
        else:
            db.session.add(Price(model=model, price=price))
            created += 1
    db.session.commit()
    log_event("price.bulk", {"created": created, "updated": updated, "skipped": skipped})
    return jsonify(ok=True, created=created, updated=updated, skipped=skipped)

@app.post("/admin_api/prices/defaults")
@admin_required
def admin_price_defaults():
    touched = 0
    for m, p in DEFAULT_PRICES.items():
        obj = Price.query.filter_by(model=m).first()
        if obj:
            continue
        db.session.add(Price(model=m, price=p))
        touched += 1
    db.session.commit()
    log_event("price.defaults", {"added": touched})
    return jsonify(ok=True, added=touched)

# ---- Config ----
@app.get("/admin_api/config")
@admin_required
def admin_config_get():
    cfg = Config.query.order_by(Config.id.asc()).first()
    if not cfg:
        cfg = Config()
        db.session.add(cfg)
        db.session.commit()
    return jsonify(ok=True, config={
        "latest_version": cfg.latest_version,
        "force_update": bool(cfg.force_update),
        "maintenance": bool(cfg.maintenance),
        "maintenance_message": cfg.maintenance_message or "",
        "update_description": cfg.update_description or "",
        "update_links": cfg.update_links or "[]",
        "updated_at": fmt_dt(cfg.updated_at or cfg.updated_at),
    })

@app.post("/admin_api/config")
@admin_required
def admin_config_set():
    body = request.get_json(force=True, silent=True) or {}
    cfg = Config.query.order_by(Config.id.asc()).first()
    if not cfg:
        cfg = Config()
        db.session.add(cfg)

    if "latest_version" in body:
        cfg.latest_version = str(body.get("latest_version") or cfg.latest_version)
    if "force_update" in body:
        cfg.force_update = bool(body.get("force_update"))
    if "maintenance" in body:
        cfg.maintenance = bool(body.get("maintenance"))
    if "maintenance_message" in body:
        cfg.maintenance_message = str(body.get("maintenance_message") or "")
    if "update_description" in body:
        cfg.update_description = str(body.get("update_description") or "")
    if "update_links" in body:
        # збережемо як JSON-рядок
        links = body.get("update_links")
        if isinstance(links, list):
            cfg.update_links = json.dumps(links, ensure_ascii=False)
        else:
            cfg.update_links = str(links or "[]")
    cfg.updated_at = utcnow()
    db.session.commit()
    log_event("config.update", {})
    return jsonify(ok=True)

# ---- Activity ----
@app.get("/admin_api/logs")
@admin_required
def admin_logs():
    page = int(request.args.get("page", 1))
    page_size = min(100, int(request.args.get("page_size", 20)))
    query = ActivityLog.query.order_by(ActivityLog.id.desc())
    total, pages, items = paginate(query, page, page_size)
    data = [{"id": it.id, "when": fmt_dt(it.when), "event": it.event, "meta": it.meta or ""} for it in items]
    return jsonify(ok=True, page=page, pages=pages, total=total, items=data)

# ---------- Run ----------
if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)