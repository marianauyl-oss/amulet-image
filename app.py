# -*- coding: utf-8 -*-
import os, json
from datetime import datetime
from io import BytesIO
from flask import Flask, request, jsonify, send_from_directory, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from dotenv import load_dotenv
from sqlalchemy import inspect

# ==========================================================
# 🧿 Amulet | Seedream Backend v3.8 — FULL Admin API + Auto-Fix
# ==========================================================

load_dotenv()
app = Flask(__name__, static_folder='static')
CORS(app)

# ---- ENV / CONFIG ----
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///amulet.db')
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'amulet-secret')
db = SQLAlchemy(app)

ADMIN_USER = os.getenv('ADMIN_USER', 'admin')
ADMIN_PASS = os.getenv('ADMIN_PASS', 'admin123')

# ==========================================================
# MODELS
# ==========================================================
class License(db.Model):
    __tablename__ = 'license'
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(255), unique=True, nullable=False)
    mac_id = db.Column(db.String(255))
    status = db.Column(db.String(50), default="active")  # active|inactive|banned (використання на фронті — як active)
    credit = db.Column(db.Integer, default=0)
    active = db.Column(db.Boolean, default=True)
    last_active = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)

class ApiKey(db.Model):
    __tablename__ = 'api_key'
    id = db.Column(db.Integer, primary_key=True)
    api_key = db.Column(db.String(255), unique=True, nullable=False)
    status = db.Column(db.String(50), default='active')
    in_use = db.Column(db.Boolean, default=False)
    last_used = db.Column(db.DateTime)
    note = db.Column(db.Text)

class Voice(db.Model):
    __tablename__ = 'voice'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    voice_id = db.Column(db.String(255), unique=True, nullable=False)
    active = db.Column(db.Boolean, default=True)

class Config(db.Model):
    __tablename__ = 'config'
    id = db.Column(db.Integer, primary_key=True)
    latest_version = db.Column(db.String(50), default='1.0.0')
    force_update = db.Column(db.Boolean, default=False)
    maintenance = db.Column(db.Boolean, default=False)
    maintenance_message = db.Column(db.Text, default='')
    update_description = db.Column(db.Text, default='')
    update_links = db.Column(db.Text, default='[]')
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

class ActivityLog(db.Model):
    __tablename__ = 'activity_log'
    id = db.Column(db.Integer, primary_key=True)
    license_id = db.Column(db.Integer)
    action = db.Column(db.String(50))
    char_count = db.Column(db.Integer, default=0)
    details = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ==========================================================
# AUTO SCHEMA FIX
# ==========================================================
def _ensure_columns():
    engine = db.engine
    insp = inspect(engine)

    def ensure(table, col, ddl):
        try:
            cols = {c["name"] for c in insp.get_columns(table)}
            if col not in cols:
                with engine.begin() as conn:
                    conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")
                print(f"🛠 Added column: {table}.{col}")
        except Exception as e:
            print(f"⚠️ Skip ensure {table}.{col}: {e}")

    # License
    ensure("license", "status", "VARCHAR(50) DEFAULT 'active'")
    ensure("license", "active", "BOOLEAN DEFAULT 1")
    ensure("license", "last_active", "DATETIME")

    # ApiKey
    ensure("api_key", "in_use", "BOOLEAN DEFAULT 0")
    ensure("api_key", "note", "TEXT")
    ensure("api_key", "last_used", "DATETIME")

    # Voice (in case of old DBs)
    try:
        insp.get_columns("voice")
    except Exception:
        with engine.begin() as conn:
            conn.exec_driver_sql("""
            CREATE TABLE IF NOT EXISTS voice (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              name VARCHAR(255) NOT NULL,
              voice_id VARCHAR(255) UNIQUE NOT NULL,
              active BOOLEAN DEFAULT 1
            )
            """)

    # Config
    ensure("config", "updated_at", "DATETIME DEFAULT CURRENT_TIMESTAMP")

with app.app_context():
    db.create_all()
    _ensure_columns()
    if not Config.query.first():
        db.session.add(Config(update_description="Initial config"))
        db.session.commit()

# ==========================================================
# BASIC AUTH
# ==========================================================
def _is_authed():
    """Accepts Basic Auth or X-Admin-User/Pass headers (for fetch)."""
    auth = request.authorization
    if auth and auth.username == ADMIN_USER and auth.password == ADMIN_PASS:
        return True
    u = request.headers.get("X-Admin-User")
    p = request.headers.get("X-Admin-Pass")
    if u == ADMIN_USER and p == ADMIN_PASS:
        return True
    return False

def _need_auth():
    return jsonify({"ok": False, "msg": "Unauthorized"}), 401

# ==========================================================
# PUBLIC API (client)
# ==========================================================
@app.route("/api", methods=["POST"])
def api_main():
    req = request.get_json(force=True, silent=True) or {}
    act = (req.get("action") or "").lower()

    def jerr(msg, code=400): return jsonify({"ok": False, "msg": msg}), code

    try:
        if act == "check":
            key = (req.get("key") or "").strip()
            mac = (req.get("mac") or "").strip()
            if not key or not mac: return jerr("key/mac required")
            lic = License.query.filter_by(key=key).first()
            if not lic: return jerr("License not found", 404)
            if lic.status != "active": return jerr("Inactive license", 403)
            if lic.mac_id and lic.mac_id != mac: return jerr("License bound to another device", 403)
            if not lic.mac_id: lic.mac_id = mac
            lic.last_active = datetime.utcnow()
            db.session.commit()
            return jsonify({"ok": True, "credit": lic.credit, "status": lic.status})

        elif act == "debit":
            key = (req.get("key") or "").strip()
            mac = (req.get("mac") or "").strip()
            model = (req.get("model") or "").strip()
            count = int(req.get("count") or 0)
            if not key or not mac or not model or count <= 0: return jerr("Invalid params")
            lic = License.query.filter_by(key=key).first()
            if not lic: return jerr("License not found", 404)
            if lic.mac_id != mac: return jerr("MAC mismatch", 403)
            if lic.credit < count: return jsonify({"ok": False, "msg": "Insufficient credit", "credit": lic.credit}), 402
            lic.credit -= count
            lic.last_active = datetime.utcnow()
            db.session.add(ActivityLog(license_id=lic.id, action="debit", char_count=count, details=f"model={model}"))
            db.session.commit()
            return jsonify({"ok": True, "debited": count, "credit": lic.credit})

        elif act == "refund":
            key = (req.get("key") or "").strip()
            mac = (req.get("mac") or "").strip()
            count = int(req.get("count") or 0)
            reason = (req.get("reason") or "").strip()
            lic = License.query.filter_by(key=key).first()
            if not lic: return jerr("License not found", 404)
            if lic.mac_id != mac: return jerr("MAC mismatch", 403)
            lic.credit += count
            db.session.add(ActivityLog(license_id=lic.id, action="refund", char_count=count, details=reason))
            db.session.commit()
            return jsonify({"ok": True, "refunded": count, "credit": lic.credit})

        elif act == "next_api_key":
            k = ApiKey.query.filter_by(status="active", in_use=False).first()
            if not k: return jerr("No active free API keys", 404)
            k.in_use = True; k.last_used = datetime.utcnow(); db.session.commit()
            return jsonify({"ok": True, "api_key": k.api_key})

        elif act == "release_api_key":
            x = (req.get("api_key") or "").strip()
            k = ApiKey.query.filter_by(api_key=x).first()
            if not k: return jerr("API key not found", 404)
            k.in_use = False; k.last_used = datetime.utcnow(); db.session.commit()
            return jsonify({"ok": True, "status": "released"})

        elif act == "deactivate_api_key":
            x = (req.get("api_key") or "").strip()
            k = ApiKey.query.filter_by(api_key=x).first()
            if not k: return jerr("API key not found", 404)
            k.status = "inactive"; k.in_use = False; db.session.commit()
            return jsonify({"ok": True, "status": "inactive"})

        elif act == "get_config":
            c = Config.query.first()
            return jsonify({"ok": True, "config": {
                "latest_version": c.latest_version,
                "force_update": c.force_update,
                "maintenance": c.maintenance,
                "maintenance_message": c.maintenance_message,
                "update_description": c.update_description,
                "update_links": json.loads(c.update_links or "[]")
            }})

        elif act == "get_prices":
            # базова відповідь; за потреби зробимо таблицю "prices"
            return jsonify({"ok": True, "prices": {
                "seedream-v4": 1, "flux-pro-v1-1": 2, "imagen3": 2, "classic-fast": 1, "_default": 1
            }})
        else:
            return jerr("Unknown action")
    except Exception as e:
        return jsonify({"ok": False, "msg": f"Internal error: {e}"}), 500

# ==========================================================
# ADMIN API (фронтенд)
# ==========================================================
@app.route("/admin_api/login", methods=["GET", "POST"])
def admin_login():
    # Дозволяємо як JSON POST, так і GET з Basic/X-Admin header — щоб не було 404/405
    if request.method == "POST":
        data = request.get_json(force=True, silent=True) or {}
        if data.get("username") == ADMIN_USER and data.get("password") == ADMIN_PASS:
            return jsonify({"ok": True})
        return jsonify({"ok": False, "msg": "Invalid credentials"}), 401
    # GET — просто перевірка заголовків
    if _is_authed():
        return jsonify({"ok": True})
    return _need_auth()

# ---- LICENSES ----
@app.route("/admin_api/licenses", methods=["GET", "POST"])
def admin_licenses():
    if not _is_authed(): return _need_auth()

    if request.method == "GET":
        q = (request.args.get("q") or "").strip()
        query = License.query
        if q:
            like = f"%{q}%"
            query = query.filter(License.key.ilike(like) | License.mac_id.ilike(like))
        items = query.order_by(License.id.desc()).all()
        return jsonify([{
            "id": l.id, "key": l.key, "status": l.status, "credit": l.credit, "active": l.active,
            "mac_id": l.mac_id, "last_active": l.last_active.isoformat() if l.last_active else "",
            "created_at": l.created_at.isoformat() if l.created_at else ""
        } for l in items])

    data = request.get_json(force=True)
    key = (data.get("key") or "").strip()
    if not key: return jsonify({"ok": False, "msg": "Key is required"}), 400
    lic = License.query.filter_by(key=key).first()
    if not lic:
        lic = License(key=key)
        db.session.add(lic)
    lic.mac_id = data.get("mac_id") or lic.mac_id
    if "credit" in data: lic.credit = int(data.get("credit") or 0)
    if "status" in data: lic.status = data.get("status") or "active"
    if "active" in data: lic.active = bool(data.get("active"))
    db.session.commit()
    return jsonify({"ok": True, "msg": "License saved"})

@app.route("/admin_api/licenses/<int:lid>", methods=["PUT", "DELETE"])
def admin_license_edit(lid):
    if not _is_authed(): return _need_auth()
    lic = License.query.get(lid)
    if not lic: return jsonify({"ok": False, "msg": "Not found"}), 404
    if request.method == "DELETE":
        db.session.delete(lic); db.session.commit()
        return jsonify({"ok": True, "msg": "Deleted"})
    data = request.get_json(force=True)
    for k in ["key", "mac_id", "status"]:
        if k in data and data[k] is not None:
            setattr(lic, k, data[k])
    if "credit" in data: lic.credit = int(data.get("credit") or 0)
    if "active" in data: lic.active = bool(data.get("active"))
    db.session.commit()
    return jsonify({"ok": True, "msg": "Updated"})

@app.route("/admin_api/licenses/filter")
def admin_filter_licenses():
    if not _is_authed(): return _need_auth()
    min_credit = request.args.get("min_credit", type=int)
    max_credit = request.args.get("max_credit", type=int)
    active = request.args.get("active")  # "true"|"false"|None
    q = License.query
    if min_credit is not None: q = q.filter(License.credit >= min_credit)
    if max_credit is not None: q = q.filter(License.credit <= max_credit)
    if active in ("true", "false"): q = q.filter(License.active == (active == "true"))
    res = q.order_by(License.id.desc()).all()
    return jsonify([{
        "id": l.id, "key": l.key, "credit": l.credit, "active": l.active, "mac_id": l.mac_id
    } for l in res])

# ---- API KEYS ----
@app.route("/admin_api/apikeys", methods=["GET", "POST"])
def admin_apikeys():
    if not _is_authed(): return _need_auth()

    if request.method == "GET":
        keys = ApiKey.query.order_by(ApiKey.id.desc()).all()
        return jsonify([{
            "id": k.id, "api_key": k.api_key, "status": k.status,
            "in_use": k.in_use, "last_used": k.last_used.isoformat() if k.last_used else "",
            "note": k.note or ""
        } for k in keys])

    # POST: JSON або multipart (.txt — кожен ключ з нового рядка)
    if request.content_type and "multipart/form-data" in request.content_type:
        file = request.files.get("file")
        if not file: return jsonify({"ok": False, "msg": "No file"}), 400
        lines = file.read().decode("utf-8", errors="ignore").splitlines()
        cnt = 0
        for line in lines:
            s = line.strip()
            if not s: continue
            if not ApiKey.query.filter_by(api_key=s).first():
                db.session.add(ApiKey(api_key=s))
                cnt += 1
        db.session.commit()
        return jsonify({"ok": True, "imported": cnt})

    data = request.get_json(force=True)
    s = (data.get("api_key") or "").strip()
    if not s: return jsonify({"ok": False, "msg": "api_key required"}), 400
    if not ApiKey.query.filter_by(api_key=s).first():
        db.session.add(ApiKey(api_key=s))
        db.session.commit()
    return jsonify({"ok": True, "msg": "Saved"})

@app.route("/admin_api/apikeys/<int:kid>", methods=["PUT", "DELETE"])
def admin_apikeys_edit(kid):
    if not _is_authed(): return _need_auth()
    k = ApiKey.query.get(kid)
    if not k: return jsonify({"ok": False, "msg": "Not found"}), 404
    if request.method == "DELETE":
        db.session.delete(k); db.session.commit()
        return jsonify({"ok": True, "msg": "Deleted"})
    data = request.get_json(force=True)
    if "api_key" in data and data["api_key"]:
        k.api_key = data["api_key"]
    if "status" in data and data["status"]:
        k.status = data["status"]
    if "in_use" in data:
        k.in_use = bool(data["in_use"])
    if "note" in data:
        k.note = data["note"]
    db.session.commit()
    return jsonify({"ok": True, "msg": "Updated"})

# ---- VOICES ----
@app.route("/admin_api/voices", methods=["GET", "POST", "PUT"])
def admin_voices():
    if not _is_authed(): return _need_auth()
    if request.method == "GET":
        vs = Voice.query.order_by(Voice.id.desc()).all()
        return jsonify([{"id": v.id, "name": v.name, "voice_id": v.voice_id, "active": v.active} for v in vs])
    if request.method == "POST":
        d = request.get_json(force=True)
        name = (d.get("name") or "").strip()
        vid = (d.get("voice_id") or "").strip()
        if not name or not vid: return jsonify({"ok": False, "msg": "name/voice_id required"}), 400
        if not Voice.query.filter_by(voice_id=vid).first():
            db.session.add(Voice(name=name, voice_id=vid, active=bool(d.get("active", True))))
            db.session.commit()
        return jsonify({"ok": True, "msg": "Voice saved"})
    if request.method == "PUT":
        d = request.get_json(force=True)
        v = Voice.query.get(int(d.get("id") or 0))
        if not v: return jsonify({"ok": False, "msg": "Not found"}), 404
        if "name" in d and d["name"]: v.name = d["name"]
        if "voice_id" in d and d["voice_id"]: v.voice_id = d["voice_id"]
        if "active" in d: v.active = bool(d["active"])
        db.session.commit()
        return jsonify({"ok": True, "msg": "Updated"})

@app.route("/admin_api/voices/<int:vid>", methods=["DELETE"])
def admin_delete_voice(vid):
    if not _is_authed(): return _need_auth()
    v = Voice.query.get(vid)
    if not v: return jsonify({"ok": False, "msg": "Not found"}), 404
    db.session.delete(v); db.session.commit()
    return jsonify({"ok": True, "msg": "Deleted"})

@app.route("/admin_api/voices/delete_all", methods=["DELETE"])
def admin_delete_all_voices():
    if not _is_authed(): return _need_auth()
    Voice.query.delete(); db.session.commit()
    return jsonify({"ok": True, "msg": "All voices deleted"})

# ---- CONFIG ----
@app.route("/admin_api/config", methods=["GET", "PUT"])
def admin_config():
    if not _is_authed(): return _need_auth()
    c = Config.query.first()
    if request.method == "GET":
        return jsonify({
            "latest_version": c.latest_version,
            "force_update": c.force_update,
            "maintenance": c.maintenance,
            "maintenance_message": c.maintenance_message,
            "update_description": c.update_description,
            "update_links": json.loads(c.update_links or "[]")
        })
    d = request.get_json(force=True)
    if "latest_version" in d: c.latest_version = d["latest_version"]
    if "force_update" in d: c.force_update = bool(d["force_update"])
    if "maintenance" in d: c.maintenance = bool(d["maintenance"])
    if "maintenance_message" in d: c.maintenance_message = d["maintenance_message"]
    if "update_description" in d: c.update_description = d["update_description"]
    if "update_links" in d:
        try: c.update_links = json.dumps(d["update_links"], ensure_ascii=False)
        except: c.update_links = json.dumps([x.strip() for x in str(d["update_links"]).split(",") if x.strip()], ensure_ascii=False)
    c.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"ok": True, "msg": "Config updated"})

# ---- LOGS & BACKUP ----
@app.route("/admin_api/logs")
def admin_logs():
    if not _is_authed(): return _need_auth()
    items = ActivityLog.query.order_by(ActivityLog.created_at.desc()).limit(200).all()
    return jsonify([{
        "id": x.id, "license_id": x.license_id, "action": x.action, "char_count": x.char_count,
        "details": x.details, "created_at": x.created_at.isoformat()
    } for x in items])

@app.route("/admin_api/backup")
def admin_backup():
    if not _is_authed(): return _need_auth()
    data = {
        "licenses": [{"key": x.key, "credit": x.credit, "status": x.status, "active": x.active} for x in License.query.all()],
        "api_keys": [{"api_key": k.api_key, "status": k.status, "in_use": k.in_use, "note": k.note} for k in ApiKey.query.all()],
        "voices":   [{"name": v.name, "voice_id": v.voice_id, "active": v.active} for v in Voice.query.all()],
        "config":   [{
            "latest_version": c.latest_version, "force_update": c.force_update, "maintenance": c.maintenance,
            "maintenance_message": c.maintenance_message, "update_description": c.update_description,
            "update_links": json.loads(c.update_links or "[]")
        } for c in [Config.query.first()]]
    }
    buf = BytesIO(json.dumps(data, indent=2, ensure_ascii=False).encode())
    return send_file(buf, mimetype="application/json", as_attachment=True, download_name="amulet_backup.json")

@app.route("/admin_api/backup/users")
def admin_backup_users():
    if not _is_authed(): return _need_auth()
    data = {"licenses": [
        {"key": x.key, "mac_id": x.mac_id, "credit": x.credit, "active": x.active, "status": x.status}
        for x in License.query.all()
    ]}
    buf = BytesIO(json.dumps(data, indent=2, ensure_ascii=False).encode())
    return send_file(buf, mimetype="application/json", as_attachment=True, download_name="users_backup.json")

# ==========================================================
# STATIC
# ==========================================================
@app.route("/")
@app.route("/admin")
def admin_page():
    return send_from_directory('static', 'admin.html')

@app.route("/<path:p>")
def static_files(p):
    return send_from_directory('static', p)

# ==========================================================
if __name__ == "__main__":
    # Для перезапуску локально:
    # rm amulet.db  (за потреби)
    app.run(port=3030, debug=True)