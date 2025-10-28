# -*- coding: utf-8 -*-
import os
import json
import datetime as dt
from typing import List, Dict, Any, Optional

from flask import (
    Flask, request, jsonify, send_from_directory, abort, redirect, url_for
)
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, or_

# -----------------------------------------------------------------------------
# Config / App
# -----------------------------------------------------------------------------
def _normalize_db_url(raw: str) -> str:
    if not raw:
        # Render persistent disk для SQLite
        return "sqlite:////data/app.db"
    # Додаємо явний драйвер psycopg3
    if raw.startswith("postgres://"):
        return raw.replace("postgres://", "postgresql+psycopg://", 1)
    if raw.startswith("postgresql://") and "+psycopg" not in raw:
        return raw.replace("postgresql://", "postgresql+psycopg://", 1)
    return raw

app = Flask(__name__, static_folder="static", static_url_path="")
CORS(app)

DB_URL = _normalize_db_url(os.getenv("DATABASE_URL", "").strip())
app.config["SQLALCHEMY_DATABASE_URI"] = DB_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["JSON_AS_ASCII"] = False

db = SQLAlchemy(app)

ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASS", "admin")

# -----------------------------------------------------------------------------
# Models
# -----------------------------------------------------------------------------
class License(db.Model):
    __tablename__ = "license"
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(128), unique=True, index=True, nullable=False)
    mac_id = db.Column(db.String(64), nullable=True)
    status = db.Column(db.String(32), nullable=False, default="active")  # active|inactive
    credit = db.Column(db.Integer, nullable=False, default=0)
    last_active = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=func.now())
    updated_at = db.Column(db.DateTime, nullable=False, default=func.now(), onupdate=func.now())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "key": self.key,
            "mac_id": self.mac_id or "",
            "status": self.status,
            "credit": self.credit,
            "last_active": self.last_active.isoformat() if self.last_active else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ApiKey(db.Model):
    __tablename__ = "apikey"
    id = db.Column(db.Integer, primary_key=True)
    api_key = db.Column(db.String(256), unique=True, index=True, nullable=False)
    status = db.Column(db.String(32), nullable=False, default="active")  # active|inactive
    in_use = db.Column(db.Boolean, nullable=False, default=False)
    last_used = db.Column(db.DateTime, nullable=True)
    note = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=func.now())
    updated_at = db.Column(db.DateTime, nullable=False, default=func.now(), onupdate=func.now())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "api_key": self.api_key,
            "status": self.status,
            "in_use": bool(self.in_use),
            "last_used": self.last_used.isoformat() if self.last_used else None,
            "note": self.note or "",
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Config(db.Model):
    __tablename__ = "config"
    id = db.Column(db.Integer, primary_key=True)
    latest_version = db.Column(db.String(32), nullable=False, default="2.3.3")
    force_update = db.Column(db.Boolean, nullable=False, default=False)
    maintenance = db.Column(db.Boolean, nullable=False, default=False)
    maintenance_message = db.Column(db.Text, nullable=True, default="")
    update_description = db.Column(db.Text, nullable=True, default="")
    update_links = db.Column(db.Text, nullable=True, default="[]")  # JSON array string
    updated_at = db.Column(db.DateTime, nullable=False, default=func.now(), onupdate=func.now())

    def to_dict(self) -> Dict[str, Any]:
        links = []
        try:
            links = json.loads(self.update_links or "[]")
            if not isinstance(links, list):
                links = [str(links)]
        except Exception:
            links = []
        return {
            "id": self.id,
            "latest_version": self.latest_version,
            "force_update": bool(self.force_update),
            "maintenance": bool(self.maintenance),
            "maintenance_message": self.maintenance_message or "",
            "update_description": (self.update_description or "").strip(),
            "update_links": links,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Price(db.Model):
    __tablename__ = "price"
    id = db.Column(db.Integer, primary_key=True)
    model = db.Column(db.String(128), unique=True, index=True, nullable=False)
    price = db.Column(db.Integer, nullable=False, default=1)
    updated_at = db.Column(db.DateTime, nullable=False, default=func.now(), onupdate=func.now())

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "model": self.model, "price": self.price, "updated_at": self.updated_at.isoformat() if self.updated_at else None}


class ActivityLog(db.Model):
    __tablename__ = "activitylog"
    id = db.Column(db.Integer, primary_key=True)
    action = db.Column(db.String(64), nullable=False)
    detail = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=func.now())

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "action": self.action, "detail": self.detail or "", "created_at": self.created_at.isoformat() if self.created_at else None}


# -----------------------------------------------------------------------------
# Bootstrap DB (create tables + default rows)
# -----------------------------------------------------------------------------
DEFAULT_PRICES = {
    "seedream-v4": 1,
    "flux-dev": 1,
    "flux-pro-v1-1": 2,
    "gemini-2.5-flash": 1,
    "imagen3": 2,
    "classic-fast": 1,
}

with app.app_context():
    db.create_all()

    # Ensure exactly one config row
    if not Config.query.first():
        db.session.add(Config(
            latest_version="2.3.3",
            force_update=False,
            maintenance=False,
            maintenance_message="",
            update_description="",
            update_links=json.dumps([]),
        ))
        db.session.commit()

    # Seed default prices if empty
    if Price.query.count() == 0:
        for m, p in DEFAULT_PRICES.items():
            db.session.add(Price(model=m, price=int(p)))
        db.session.commit()


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def _log(action: str, detail: str = "") -> None:
    try:
        db.session.add(ActivityLog(action=action, detail=detail[:2000]))
        db.session.commit()
    except Exception:
        db.session.rollback()

def _require_auth():
    auth = request.authorization
    if not auth or auth.username != ADMIN_USER or auth.password != ADMIN_PASS:
        return False
    return True

def admin_required(fn):
    from functools import wraps
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not _require_auth():
            resp = jsonify({"ok": False, "msg": "Unauthorized"})
            resp.status_code = 401
            resp.headers["WWW-Authenticate"] = 'Basic realm="Admin"'
            return resp
        return fn(*args, **kwargs)
    return wrapper


# -----------------------------------------------------------------------------
# Static / Health
# -----------------------------------------------------------------------------
@app.route("/")
def index():
    # зручно одразу відкривати адмінку
    return redirect(url_for("admin_html"))

@app.route("/admin")
def admin_html():
    return send_from_directory(app.static_folder, "admin.html")

@app.route("/healthz")
def health():
    return jsonify({"ok": True, "time": dt.datetime.utcnow().isoformat(), "db": DB_URL.split(":")[0]})


# -----------------------------------------------------------------------------
# Admin Auth
# -----------------------------------------------------------------------------
@app.route("/admin_api/login")
@admin_required
def admin_login():
    return jsonify({"ok": True})


# -----------------------------------------------------------------------------
# Licenses
# -----------------------------------------------------------------------------
@app.route("/admin_api/licenses", methods=["GET"])
@admin_required
def admin_licenses_list():
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "").strip().lower()
    min_credit = request.args.get("min_credit", "").strip()
    max_credit = request.args.get("max_credit", "").strip()

    query = License.query
    if q:
        like = f"%{q}%"
        query = query.filter(or_(License.key.ilike(like), License.mac_id.ilike(like)))
    if status in ("active", "inactive"):
        query = query.filter(License.status == status)
    if min_credit.isdigit():
        query = query.filter(License.credit >= int(min_credit))
    if max_credit.isdigit():
        query = query.filter(License.credit <= int(max_credit))

    items = query.order_by(License.id.desc()).all()
    return jsonify({"ok": True, "items": [i.to_dict() for i in items]})

@app.route("/admin_api/licenses", methods=["POST"])
@admin_required
def admin_licenses_create():
    """
    Приймає:
      - JSON: { "keys": "AAA\nBBB\nCCC", "status": "active", "credit": 100 }
      - або form-data / x-www-form-urlencoded з тими ж полями
      - також підтримує upload файлу txt через поле 'file'
    """
    payload = request.get_json(silent=True) or {}
    text_keys = ""
    status = (payload.get("status") or request.form.get("status") or "active").strip().lower()
    credit_val = payload.get("credit", request.form.get("credit", 0))
    try:
        credit = int(credit_val)
    except Exception:
        credit = 0

    # file?
    if "file" in request.files and request.files["file"]:
        try:
            text_keys = request.files["file"].read().decode("utf-8", errors="ignore")
        except Exception:
            text_keys = ""
    else:
        # keys string or single key
        text_keys = (payload.get("keys") or request.form.get("keys") or "").strip()
        if not text_keys:
            one_key = (payload.get("key") or request.form.get("key") or "").strip()
            if one_key:
                text_keys = one_key

    if not text_keys:
        return jsonify({"ok": False, "msg": "No keys provided"}), 400

    lines = [k.strip() for k in text_keys.replace("\r", "").split("\n")]
    keys = [k for k in lines if k]
    if not keys:
        return jsonify({"ok": False, "msg": "Empty keys"}), 400

    added, updated, skipped = 0, 0, 0
    for k in keys:
        ex = License.query.filter_by(key=k).first()
        if ex:
            # оновлюємо лише якщо явний кредит/статус передано
            changed = False
            if status in ("active", "inactive") and ex.status != status:
                ex.status = status
                changed = True
            if credit is not None and isinstance(credit, int) and credit > ex.credit:
                # якщо переданий credit більший — встановимо (не зменшуємо тут)
                ex.credit = credit
                changed = True
            if changed:
                updated += 1
            else:
                skipped += 1
        else:
            db.session.add(License(key=k, status=(status if status in ("active", "inactive") else "active"), credit=credit))
            added += 1
    try:
        db.session.commit()
        _log("licenses.create_bulk", f"added={added}, updated={updated}, skipped={skipped}")
        return jsonify({"ok": True, "added": added, "updated": updated, "skipped": skipped})
    except Exception as e:
        db.session.rollback()
        return jsonify({"ok": False, "msg": str(e)}), 500

@app.route("/admin_api/licenses/<int:lid>", methods=["PATCH"])
@admin_required
def admin_license_patch(lid: int):
    row = License.query.get(lid)
    if not row:
        return jsonify({"ok": False, "msg": "Not found"}), 404
    payload = request.get_json(silent=True) or {}

    status = (payload.get("status") or "").strip().lower()
    if status in ("active", "inactive"):
        row.status = status

    if "credit" in payload:
        try:
            row.credit = int(payload.get("credit"))
        except Exception:
            pass
    if "delta" in payload:
        try:
            row.credit = max(0, int(row.credit) + int(payload.get("delta")))
        except Exception:
            pass
    if "mac_id" in payload:
        row.mac_id = (payload.get("mac_id") or "").strip()
    if payload.get("unbind_mac"):
        row.mac_id = None

    try:
        db.session.commit()
        _log("licenses.patch", f"id={row.id}")
        return jsonify({"ok": True, "item": row.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({"ok": False, "msg": str(e)}), 500

@app.route("/admin_api/licenses/<int:lid>", methods=["DELETE"])
@admin_required
def admin_license_delete(lid: int):
    row = License.query.get(lid)
    if not row:
        return jsonify({"ok": False, "msg": "Not found"}), 404
    try:
        db.session.delete(row)
        db.session.commit()
        _log("licenses.delete", f"id={lid}")
        return jsonify({"ok": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"ok": False, "msg": str(e)}), 500


# -----------------------------------------------------------------------------
# API Keys (з масовим імпортом .txt)
# -----------------------------------------------------------------------------
@app.route("/admin_api/apikeys", methods=["GET"])
@admin_required
def admin_apikeys_list():
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "").strip().lower()
    in_use = request.args.get("in_use", "").strip().lower()

    query = ApiKey.query
    if q:
        like = f"%{q}%"
        query = query.filter(or_(ApiKey.api_key.ilike(like), ApiKey.note.ilike(like)))
    if status in ("active", "inactive"):
        query = query.filter(ApiKey.status == status)
    if in_use in ("yes", "true", "1"):
        query = query.filter(ApiKey.in_use.is_(True))
    elif in_use in ("no", "false", "0"):
        query = query.filter(ApiKey.in_use.is_(False))

    items = query.order_by(ApiKey.id.desc()).all()
    return jsonify({"ok": True, "items": [i.to_dict() for i in items]})

def _parse_keys_text(text: str) -> List[str]:
    lines = [x.strip() for x in (text or "").replace("\r", "").split("\n")]
    return [x for x in lines if x]

@app.route("/admin_api/apikeys", methods=["POST"])
@admin_required
def admin_apikeys_create():
    """
    JSON/Form:
      - "keys": "k1\nk2\nk3" або "key": "single"
      - "status": "active|inactive" (default active)
      - "note": "..."
    """
    payload = request.get_json(silent=True) or {}
    status = (payload.get("status") or request.form.get("status") or "active").strip().lower()
    note = (payload.get("note") or request.form.get("note") or "").strip()

    text_keys = (payload.get("keys") or request.form.get("keys") or "").strip()
    if not text_keys:
        one = (payload.get("key") or request.form.get("key") or "").strip()
        text_keys = one

    keys = _parse_keys_text(text_keys)
    if not keys:
        return jsonify({"ok": False, "msg": "No keys provided"}), 400

    added, skipped = 0, 0
    for k in keys:
        if ApiKey.query.filter_by(api_key=k).first():
            skipped += 1
            continue
        db.session.add(ApiKey(api_key=k, status=(status if status in ("active", "inactive") else "active"), note=note))
        added += 1
    try:
        db.session.commit()
        _log("apikeys.create_bulk", f"added={added}, skipped={skipped}")
        return jsonify({"ok": True, "added": added, "skipped": skipped})
    except Exception as e:
        db.session.rollback()
        return jsonify({"ok": False, "msg": str(e)}), 500

@app.route("/admin_api/apikeys/upload", methods=["POST"])
@admin_required
def admin_apikeys_upload():
    """
    Upload .txt file (field name: 'file'), 1 ключ у рядку.
    """
    if "file" not in request.files or not request.files["file"]:
        return jsonify({"ok": False, "msg": "No file"}), 400
    try:
        text = request.files["file"].read().decode("utf-8", errors="ignore")
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 400
    keys = _parse_keys_text(text)
    if not keys:
        return jsonify({"ok": False, "msg": "Empty file"}), 400

    added, skipped = 0, 0
    for k in keys:
        if ApiKey.query.filter_by(api_key=k).first():
            skipped += 1
            continue
        db.session.add(ApiKey(api_key=k, status="active", in_use=False))
        added += 1
    try:
        db.session.commit()
        _log("apikeys.upload", f"added={added}, skipped={skipped}")
        return jsonify({"ok": True, "added": added, "skipped": skipped})
    except Exception as e:
        db.session.rollback()
        return jsonify({"ok": False, "msg": str(e)}), 500

@app.route("/admin_api/apikeys/<int:aid>", methods=["PATCH"])
@admin_required
def admin_apikey_patch(aid: int):
    row = ApiKey.query.get(aid)
    if not row:
        return jsonify({"ok": False, "msg": "Not found"}), 404
    payload = request.get_json(silent=True) or {}

    status = (payload.get("status") or "").strip().lower()
    if status in ("active", "inactive"):
        row.status = status
    if "in_use" in payload:
        row.in_use = bool(payload.get("in_use"))
    if "note" in payload:
        row.note = (payload.get("note") or "").strip()
    if payload.get("touch_last_used"):
        row.last_used = dt.datetime.utcnow()

    try:
        db.session.commit()
        _log("apikeys.patch", f"id={row.id}")
        return jsonify({"ok": True, "item": row.to_dict()})
    except Exception as e:
        db.session.rollback
        return jsonify({"ok": False, "msg": str(e)}), 500

@app.route("/admin_api/apikeys/<int:aid>", methods=["DELETE"])
@admin_required
def admin_apikey_delete(aid: int):
    row = ApiKey.query.get(aid)
    if not row:
        return jsonify({"ok": False, "msg": "Not found"}), 404
    try:
        db.session.delete(row)
        db.session.commit()
        _log("apikeys.delete", f"id={aid}")
        return jsonify({"ok": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"ok": False, "msg": str(e)}), 500


# -----------------------------------------------------------------------------
# Prices (вкладка замість Voices)
# -----------------------------------------------------------------------------
@app.route("/admin_api/prices", methods=["GET"])
@admin_required
def admin_prices_list():
    items = Price.query.order_by(Price.model.asc()).all()
    return jsonify({"ok": True, "items": [i.to_dict() for i in items]})

@app.route("/admin_api/prices", methods=["POST"])
@admin_required
def admin_prices_upsert():
    """
    JSON:
      - single: { "model": "flux-dev", "price": 2 }
      - bulk:   { "items": [ { "model": "...", "price": 1 }, ... ] }
    """
    payload = request.get_json(silent=True) or {}
    items = []
    if "items" in payload and isinstance(payload["items"], list):
        items = payload["items"]
    elif "model" in payload and "price" in payload:
        items = [ {"model": payload.get("model"), "price": payload.get("price")} ]
    else:
        return jsonify({"ok": False, "msg": "Provide model/price or items[]"}), 400

    upserted, errors = 0, []
    for it in items:
        model = str(it.get("model") or "").strip()
        try:
            price = int(it.get("price"))
        except Exception:
            price = None
        if not model or price is None or price <= 0:
            errors.append({"model": model, "msg": "invalid"})
            continue
        row = Price.query.filter_by(model=model).first()
        if row:
            row.price = price
        else:
            db.session.add(Price(model=model, price=price))
        upserted += 1
    try:
        db.session.commit()
        _log("prices.upsert", f"count={upserted}")
        return jsonify({"ok": True, "upserted": upserted, "errors": errors})
    except Exception as e:
        db.session.rollback()
        return jsonify({"ok": False, "msg": str(e)}), 500

@app.route("/admin_api/prices/<string:model>", methods=["DELETE"])
@admin_required
def admin_prices_delete(model: str):
    row = Price.query.filter_by(model=model).first()
    if not row:
        return jsonify({"ok": False, "msg": "Not found"}), 404
    try:
        db.session.delete(row)
        db.session.commit()
        _log("prices.delete", model)
        return jsonify({"ok": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"ok": False, "msg": str(e)}), 500


# -----------------------------------------------------------------------------
# Config
# -----------------------------------------------------------------------------
@app.route("/admin_api/config", methods=["GET"])
@admin_required
def admin_config_get():
    cfg = Config.query.first()
    return jsonify({"ok": True, "item": cfg.to_dict()})

@app.route("/admin_api/config", methods=["POST"])
@admin_required
def admin_config_set():
    payload = request.get_json(silent=True) or {}
    cfg = Config.query.first()
    if not cfg:
        cfg = Config()
        db.session.add(cfg)

    if "latest_version" in payload:
        cfg.latest_version = str(payload.get("latest_version") or cfg.latest_version)
    if "force_update" in payload:
        cfg.force_update = bool(payload.get("force_update"))
    if "maintenance" in payload:
        cfg.maintenance = bool(payload.get("maintenance"))
    if "maintenance_message" in payload:
        cfg.maintenance_message = str(payload.get("maintenance_message") or "")
    if "update_description" in payload:
        cfg.update_description = str(payload.get("update_description") or "")

    if "update_links" in payload:
        links = payload.get("update_links")
        if isinstance(links, list):
            try:
                cfg.update_links = json.dumps(links, ensure_ascii=False)
            except Exception:
                cfg.update_links = "[]"
        elif isinstance(links, str):
            # приймаємо або JSON, або коми
            s = links.strip()
            if s.startswith("["):
                try:
                    json.loads(s)  # валідність
                    cfg.update_links = s
                except Exception:
                    cfg.update_links = "[]"
            else:
                arr = [x.strip() for x in s.split(",") if x.strip()]
                cfg.update_links = json.dumps(arr, ensure_ascii=False)

    try:
        db.session.commit()
        _log("config.set", "updated")
        return jsonify({"ok": True, "item": cfg.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({"ok": False, "msg": str(e)}), 500


# -----------------------------------------------------------------------------
# Logs
# -----------------------------------------------------------------------------
@app.route("/admin_api/logs", methods=["GET"])
@admin_required
def admin_logs():
    limit = request.args.get("limit", "100")
    try:
        n = max(1, min(500, int(limit)))
    except Exception:
        n = 100
    rows = ActivityLog.query.order_by(ActivityLog.id.desc()).limit(n).all()
    return jsonify({"ok": True, "items": [r.to_dict() for r in rows]})


# -----------------------------------------------------------------------------
# Run (local)
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    # Локальний запуск: DEBUG + SQLite у ./app.db
    if not os.getenv("DATABASE_URL"):
        app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///app.db"
        with app.app_context():
            db.create_all()
            if Price.query.count() == 0:
                for m, p in DEFAULT_PRICES.items():
                    db.session.add(Price(model=m, price=int(p)))
                db.session.commit()
            if not Config.query.first():
                db.session.add(Config())
                db.session.commit()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True)