# DAAC Photo Hub

A free Streamlit photo intake and approval website for the Del Amo Action Committee.

## Permanent storage flow

1. Team members upload through the code-protected Streamlit website.
2. The original files are stored permanently in the Google Drive `Pending Approval` folder.
3. An organizer reviews each batch and moves the same files into the final Drive folder.
4. Photos selected for the album are displayed directly from Google Drive.

There is no Supabase, Jotform, Dropbox, duplicate file store, or paid hosting requirement.

## Streamlit secrets

Add these in **Streamlit Community Cloud → App settings → Secrets**:

```toml
UPLOAD_ACCESS_CODE = "choose-an-upload-code"
ADMIN_ACCESS_CODE = "choose-a-different-admin-code"
GOOGLE_SERVICE_ACCOUNT_JSON = '''{"type":"service_account","project_id":"..."}'''
```

The Google service account must have Editor access to the Pending Approval folder and every destination folder.

## Run locally

```bash
python -m pip install -r requirements.txt
streamlit run app.py
```
