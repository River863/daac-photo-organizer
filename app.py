import hashlib
import io
import json
import os
import secrets
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from urllib.parse import quote

import requests
from flask import Flask, jsonify, render_template, request, session
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 250 * 1024 * 1024
app.secret_key = os.environ.get("FLASK_SECRET_KEY", secrets.token_hex(32))

SCOPES = ["https://www.googleapis.com/auth/drive"]
BUCKET = "daac-photos"
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}
CATEGORY_FOLDERS = {
    "Open Houses": "1B7N_ypgTPFEInp-w_drbnxpub5hhVG1N",
    "Community Events": "1u-Obz83I88rFPtXuiuyEtzfcfzWsMbWH",
    "Environmental & Community Projects": "1yJl5Lwsj9EqLy1DC_g1F1r9XbPISbiDr",
    "Outreach & Partnerships": "1G2n-8p4cdOYSyJ8-x6dQWX_NY9PirYEn",
    "Social Media": "1HUSk5mwaDW4jAMp6sGYZbJ_2cd2y43mR",
    "Other / Needs Sorting": "1AjD8dOem0T601hbwMnnABuBMDzG5WNv5",
}


def env(name):
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is not configured.")
    return value.rstrip("/") if name == "SUPABASE_URL" else value


def supabase_headers(content_type="application/json"):
    key = env("SUPABASE_SERVICE_ROLE_KEY")
    return {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": content_type}


def supabase_request(method, path, **kwargs):
    headers = kwargs.pop("headers", {})
    headers = {**supabase_headers(headers.pop("Content-Type", "application/json")), **headers}
    response = requests.request(method, f"{env('SUPABASE_URL')}{path}", headers=headers, timeout=90, **kwargs)
    if not response.ok:
        raise RuntimeError(response.json().get("message", response.text) if response.content else "Supabase request failed")
    return response


def drive_client():
    info = json.loads(env("GOOGLE_SERVICE_ACCOUNT_JSON"))
    credentials = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    return build("drive", "v3", credentials=credentials, cache_discovery=False)


def safe_filename(name):
    clean = Path(name or "photo").name.replace("\x00", "")
    return "".join(c for c in clean if c.isalnum() or c in "._- ").strip() or "photo"


def code_matches(value, setting):
    expected = os.environ.get(setting, "")
    return bool(expected) and secrets.compare_digest(value or "", expected)


def require_role(*roles):
    def decorator(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            if session.get("role") not in roles:
                return jsonify({"ok": False, "error": "Enter the access code first."}), 401
            return fn(*args, **kwargs)
        return wrapped
    return decorator


def public_photo_url(path):
    return f"{env('SUPABASE_URL')}/storage/v1/object/public/{BUCKET}/{quote(path, safe='/')}"


def signed_photo_url(path, expires_in=900):
    response = supabase_request(
        "POST",
        f"/storage/v1/object/sign/{BUCKET}/{quote(path, safe='/')}",
        json={"expiresIn": expires_in},
    ).json()
    signed = response.get("signedURL") or response.get("signedUrl")
    if not signed:
        raise RuntimeError("Could not create a secure photo preview.")
    return f"{env('SUPABASE_URL')}/storage/v1{signed}" if signed.startswith("/") else signed


def gallery_photos(limit=12):
    response = supabase_request(
        "GET",
        f"/rest/v1/photos?select=id,original_name,storage_path,created_at&status=eq.approved&gallery_visible=eq.true&order=created_at.desc&limit={limit}",
    )
    return [{**row, "url": public_photo_url(row["storage_path"])} for row in response.json()]


@app.get("/")
def index():
    photos = []
    try:
        photos = gallery_photos()
    except Exception:
        pass
    return render_template("index.html", categories=CATEGORY_FOLDERS.keys(), gallery=photos)


@app.post("/login")
def login():
    code = (request.get_json(silent=True) or {}).get("code", "")
    if code_matches(code, "ADMIN_ACCESS_CODE"):
        session["role"] = "admin"
    elif code_matches(code, "UPLOAD_ACCESS_CODE"):
        session["role"] = "uploader"
    else:
        return jsonify({"ok": False, "error": "That access code is not valid."}), 403
    return jsonify({"ok": True, "role": session["role"]})


@app.post("/logout")
def logout():
    session.clear()
    return jsonify({"ok": True})


@app.get("/session")
def session_status():
    return jsonify({"ok": True, "role": session.get("role")})


@app.get("/health")
def health():
    required = ["SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "GOOGLE_SERVICE_ACCOUNT_JSON", "UPLOAD_ACCESS_CODE", "ADMIN_ACCESS_CODE", "FLASK_SECRET_KEY"]
    return jsonify({"ok": True, "configured": {name: bool(os.environ.get(name)) for name in required}})


@app.post("/upload")
@require_role("uploader", "admin")
def upload():
    category = (request.form.get("category") or "").strip()
    if category not in CATEGORY_FOLDERS:
        return jsonify({"ok": False, "error": "Choose a valid category."}), 400
    files = [item for item in request.files.getlist("photos") if item and item.filename]
    if not files:
        return jsonify({"ok": False, "error": "Choose at least one photo."}), 400

    batch_payload = {
        "event_name": (request.form.get("event_name") or "").strip() or None,
        "suggested_category": category,
        "notes": (request.form.get("notes") or "").strip() or None,
        "uploader_name": (request.form.get("uploader_name") or "").strip() or None,
        "uploader_email": (request.form.get("uploader_email") or "").strip() or None,
        "status": "pending",
    }
    batch = supabase_request(
        "POST", "/rest/v1/photo_batches", json=batch_payload,
        headers={"Prefer": "return=representation"},
    ).json()[0]

    uploaded = []
    try:
        for item in files:
            mime = item.mimetype or "application/octet-stream"
            if mime not in ALLOWED_TYPES:
                raise ValueError(f"{item.filename} is not a supported image type.")
            name = safe_filename(item.filename)
            path = f"pending/{batch['id']}/{secrets.token_hex(5)}-{name}"
            data = item.read()
            supabase_request(
                "POST", f"/storage/v1/object/{BUCKET}/{quote(path, safe='/')}", data=data,
                headers={"Content-Type": mime, "x-upsert": "false"},
            )
            photo = supabase_request(
                "POST", "/rest/v1/photos",
                json={"batch_id": batch["id"], "storage_path": path, "original_name": name, "mime_type": mime, "file_size": len(data), "status": "pending", "gallery_visible": False},
                headers={"Prefer": "return=representation"},
            ).json()[0]
            uploaded.append(photo)
    except Exception:
        for photo in uploaded:
            try:
                supabase_request("DELETE", f"/storage/v1/object/{BUCKET}/{quote(photo['storage_path'], safe='/')}")
            except Exception:
                pass
        supabase_request("DELETE", f"/rest/v1/photo_batches?id=eq.{batch['id']}")
        raise

    return jsonify({"ok": True, "count": len(uploaded), "batch_id": batch["id"], "message": "Your photos were uploaded and are waiting for review."})


@app.get("/api/pending")
@require_role("admin")
def pending():
    batches = supabase_request(
        "GET", "/rest/v1/photo_batches?select=*,photos(*)&status=eq.pending&order=created_at.desc"
    ).json()
    for batch in batches:
        for photo in batch.get("photos", []):
            photo["url"] = signed_photo_url(photo["storage_path"])
    return jsonify({"ok": True, "batches": batches})


@app.post("/api/review/<batch_id>")
@require_role("admin")
def review(batch_id):
    body = request.get_json(silent=True) or {}
    decision = body.get("decision")
    category = body.get("category")
    gallery_visible = bool(body.get("gallery_visible"))
    if decision not in {"approved", "rejected"}:
        return jsonify({"ok": False, "error": "Choose approve or reject."}), 400
    if decision == "approved" and category not in CATEGORY_FOLDERS:
        return jsonify({"ok": False, "error": "Choose a destination category."}), 400

    result = supabase_request("GET", f"/rest/v1/photo_batches?select=*,photos(*)&id=eq.{batch_id}&limit=1").json()
    if not result:
        return jsonify({"ok": False, "error": "Upload batch not found."}), 404
    batch = result[0]
    drive = drive_client() if decision == "approved" else None

    for photo in batch.get("photos", []):
        old_path = photo["storage_path"]
        if decision == "approved":
            raw = supabase_request("GET", f"/storage/v1/object/authenticated/{BUCKET}/{quote(old_path, safe='/')}").content
            media = MediaIoBaseUpload(io.BytesIO(raw), mimetype=photo.get("mime_type") or "application/octet-stream", resumable=True)
            drive.files().create(
                body={"name": photo["original_name"], "parents": [CATEGORY_FOLDERS[category]], "description": f"DAAC approved upload | {batch.get('event_name') or 'Untitled event'}"},
                media_body=media, fields="id,name", supportsAllDrives=True,
            ).execute()
            new_path = f"approved/{category.replace(' ', '-').replace('&', 'and').lower()}/{batch_id}/{Path(old_path).name}"
            supabase_request("POST", "/storage/v1/object/move", json={"bucketId": BUCKET, "sourceKey": old_path, "destinationKey": new_path})
            supabase_request("PATCH", f"/rest/v1/photos?id=eq.{photo['id']}", json={"storage_path": new_path, "status": "approved", "gallery_visible": gallery_visible})
        else:
            supabase_request("DELETE", f"/storage/v1/object/{BUCKET}/{quote(old_path, safe='/')}")
            supabase_request("PATCH", f"/rest/v1/photos?id=eq.{photo['id']}", json={"status": "rejected", "gallery_visible": False})

    supabase_request(
        "PATCH", f"/rest/v1/photo_batches?id=eq.{batch_id}",
        json={"status": decision, "approved_category": category if decision == "approved" else None, "reviewed_at": datetime.now(timezone.utc).isoformat()},
    )
    return jsonify({"ok": True, "status": decision})


@app.errorhandler(413)
def too_large(_):
    return jsonify({"ok": False, "error": "That upload is too large. Choose fewer photos and try again."}), 413


@app.errorhandler(Exception)
def handle_error(error):
    app.logger.exception(error)
    return jsonify({"ok": False, "error": str(error) if app.debug else "Something went wrong. Try again or contact the organizer."}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
