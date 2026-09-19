import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

import requests
from google.oauth2 import service_account
from googleapiclient.discovery import build

ROOT = Path(__file__).resolve().parent
CONFIG = json.loads((ROOT / "config.json").read_text())
STATE_PATH = ROOT / "state" / "processed.json"
SCOPES = ["https://www.googleapis.com/auth/drive"]


def log(message):
    print(f"[{datetime.now(timezone.utc).isoformat()}] {message}", flush=True)


def require_env(name):
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def load_state():
    if not STATE_PATH.exists():
        return {"processed_submission_ids": []}
    return json.loads(STATE_PATH.read_text())


def save_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


def jotform_submissions(api_key):
    url = f"https://api.jotform.com/form/{CONFIG['form_id']}/submissions"
    response = requests.get(
        url,
        params={"apiKey": api_key, "limit": 100, "orderby": "created_at"},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("responseCode") not in (None, 200):
        raise RuntimeError(f"Jotform API error: {payload}")
    return payload.get("content", [])


def drive_client(credentials_json):
    info = json.loads(credentials_json)
    credentials = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    return build("drive", "v3", credentials=credentials, cache_discovery=False)


def answer_value(submission, question_id):
    answer = (submission.get("answers") or {}).get(str(question_id)) or {}
    return answer.get("answer")


def normalize_category(value):
    if isinstance(value, list):
        value = value[0] if value else None
    if isinstance(value, dict):
        value = value.get("value") or value.get("answer")
    return str(value).strip() if value is not None else ""


def upload_items(value):
    if not value:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    if isinstance(value, str):
        text = value.strip()
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, list) else [parsed]
        except (ValueError, TypeError):
            return [part.strip() for part in text.split(",") if part.strip()]
    return [value]


def filename_from_upload(item):
    if isinstance(item, dict):
        item = item.get("url") or item.get("name") or item.get("value") or ""
    text = str(item).strip()
    if not text:
        return ""
    path = urlparse(text).path if "://" in text else text
    return unquote(path.rstrip("/").split("/")[-1])


def escape_drive_query(value):
    return value.replace("\\", "\\\\").replace("'", "\\'")


def find_in_inbox(drive, filename):
    query = (
        f"name = '{escape_drive_query(filename)}' and "
        f"'{CONFIG['inbox_folder_id']}' in parents and trashed = false"
    )
    result = drive.files().list(
        q=query,
        fields="files(id,name,createdTime,parents)",
        orderBy="createdTime desc",
        pageSize=20,
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
    ).execute()
    files = result.get("files", [])
    return files[0] if files else None


def wait_for_file(drive, filename, attempts=12, delay=10):
    for attempt in range(1, attempts + 1):
        found = find_in_inbox(drive, filename)
        if found:
            return found
        log(f"Waiting for {filename!r} in Drive inbox ({attempt}/{attempts})")
        time.sleep(delay)
    return None


def move_file(drive, file_info, destination_id):
    parents = file_info.get("parents", [])
    drive.files().update(
        fileId=file_info["id"],
        addParents=destination_id,
        removeParents=",".join(parents),
        fields="id,name,parents",
        supportsAllDrives=True,
    ).execute()


def process_submission(drive, submission):
    submission_id = str(submission.get("id", ""))
    category = normalize_category(answer_value(submission, CONFIG["category_question_id"]))
    destination_id = CONFIG["category_folders"].get(category)
    if not destination_id:
        raise RuntimeError(f"Submission {submission_id}: unknown/missing category {category!r}")

    uploads = upload_items(answer_value(submission, CONFIG["upload_question_id"]))
    filenames = [filename_from_upload(item) for item in uploads]
    filenames = [name for name in filenames if name]
    if not filenames:
        raise RuntimeError(f"Submission {submission_id}: no uploaded filenames found")

    log(f"Submission {submission_id}: {category} -> {filenames}")
    for filename in filenames:
        file_info = wait_for_file(drive, filename)
        if not file_info:
            raise RuntimeError(f"Submission {submission_id}: {filename!r} never appeared in inbox")
        move_file(drive, file_info, destination_id)
        log(f"Moved {filename!r} to {category}")


def main():
    api_key = require_env("JOTFORM_API_KEY")
    credentials_json = require_env("GOOGLE_SERVICE_ACCOUNT_JSON")
    drive = drive_client(credentials_json)
    state = load_state()
    processed = set(state.get("processed_submission_ids", []))

    submissions = jotform_submissions(api_key)
    submissions.sort(key=lambda s: s.get("created_at", ""))
    failures = []
    changed = False

    for submission in submissions:
        submission_id = str(submission.get("id", ""))
        if not submission_id or submission_id in processed:
            continue
        try:
            process_submission(drive, submission)
            processed.add(submission_id)
            changed = True
        except Exception as exc:
            failures.append(f"{submission_id}: {exc}")
            log(f"ERROR: {failures[-1]}")

    if changed:
        state["processed_submission_ids"] = sorted(processed)
        save_state(state)

    if failures:
        log(f"Finished with {len(failures)} unprocessed submission(s). They will retry next run.")
        sys.exit(1)
    log("Photo sorting complete. No outstanding errors.")


if __name__ == "__main__":
    main()
