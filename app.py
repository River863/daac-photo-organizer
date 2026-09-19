import io
import json
import os
from datetime import datetime, timezone

from flask import Flask, jsonify, render_template, request
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 250 * 1024 * 1024

SCOPES = ['https://www.googleapis.com/auth/drive']
CATEGORY_FOLDERS = {
    'Open Houses': '1B7N_ypgTPFEInp-w_drbnxpub5hhVG1N',
    'Community Events': '1u-Obz83I88rFPtXuiuyEtzfcfzWsMbWH',
    'Environmental & Community Projects': '1yJl5Lwsj9EqLy1DC_g1F1r9XbPISbiDr',
    'Outreach & Partnerships': '1G2n-8p4cdOYSyJ8-x6dQWX_NY9PirYEn',
    'Social Media': '1HUSk5mwaDW4jAMp6sGYZbJ_2cd2y43mR',
    'Other / Needs Sorting': '1AjD8dOem0T601hbwMnnABuBMDzG5WNv5',
}


def drive_client():
    raw = os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON')
    if not raw:
        raise RuntimeError('Google Drive is not connected yet.')
    info = json.loads(raw)
    credentials = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    return build('drive', 'v3', credentials=credentials, cache_discovery=False)


@app.get('/')
def index():
    return render_template('index.html', categories=CATEGORY_FOLDERS.keys())


@app.get('/health')
def health():
    return jsonify({'ok': True, 'drive_configured': bool(os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON'))})


@app.post('/upload')
def upload():
    category = (request.form.get('category') or '').strip()
    event_name = (request.form.get('event_name') or '').strip()
    notes = (request.form.get('notes') or '').strip()
    files = [f for f in request.files.getlist('photos') if f and f.filename]

    if category not in CATEGORY_FOLDERS:
        return jsonify({'ok': False, 'error': 'Choose a valid category.'}), 400
    if not files:
        return jsonify({'ok': False, 'error': 'Choose at least one photo.'}), 400

    drive = drive_client()
    destination = CATEGORY_FOLDERS[category]
    uploaded = []
    timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%d')

    for photo in files:
        safe_name = photo.filename.rsplit('/', 1)[-1].rsplit('\\', 1)[-1]
        media = MediaIoBaseUpload(io.BytesIO(photo.read()), mimetype=photo.mimetype or 'application/octet-stream', resumable=True)
        metadata = {
            'name': safe_name,
            'parents': [destination],
            'description': f'DAAC upload | {timestamp} | {category}' + (f' | {event_name}' if event_name else '') + (f' | {notes}' if notes else ''),
        }
        created = drive.files().create(body=metadata, media_body=media, fields='id,name,webViewLink', supportsAllDrives=True).execute()
        uploaded.append({'name': created['name'], 'id': created['id']})

    return jsonify({'ok': True, 'category': category, 'count': len(uploaded), 'files': uploaded})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', '8080')))
