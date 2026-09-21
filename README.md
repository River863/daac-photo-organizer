# DAAC Photo Hub

A free Streamlit photo intake and approval website for the Del Amo Action Committee.

## Permanent storage flow

1. Team members upload through the code-protected Streamlit website.
2. The original files are stored permanently in the Google Drive `Pending Approval` folder.
3. An organizer reviews each batch and moves the same files into the final Drive folder.
4. Photos selected for the album are displayed directly from Google Drive.

There is no Supabase, Jotform, Dropbox, Google Cloud project, duplicate file store, or paid hosting requirement.

## One-time free Google Apps Script setup

1. Open Google Apps Script at https://script.google.com/home.
2. Click **New project** and replace its Code.gs file with apps_script/Code.gs from this repository.
3. Change CHANGE_THIS_TO_A_LONG_RANDOM_CODE in Code.gs to a code you make up.
4. Click **Deploy → New deployment → Web app**.
5. Set **Execute as: Me** and **Who has access: Anyone**, then deploy and copy the Web app URL.

## Streamlit secrets

Add these in **Streamlit Community Cloud → App settings → Secrets**:

```toml
UPLOAD_ACCESS_CODE = "choose-an-upload-code"
ADMIN_ACCESS_CODE = "choose-a-different-admin-code"
APPS_SCRIPT_URL = "paste-the-Web-app-URL-here"
APPS_SCRIPT_TOKEN = "the-same-code-you-put-in-Code.gs"
```

## Run locally

```bash
python -m pip install -r requirements.txt
streamlit run app.py
```
