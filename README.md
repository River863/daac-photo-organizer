# DAAC Photo Hub

A code-protected photo intake and approval website for the Del Amo Action Committee.

## What it does

- DAAC team members upload event and program photos with an upload access code.
- Photos wait in a private pending area instead of going straight into Drive.
- An organizer signs in with a separate admin code, reviews each batch, corrects its category, and approves or rejects it.
- Approved photos are copied into the selected Google Drive folder.
- Organizers can choose which approved photos appear in the homepage album.

## Required environment variables

- `FLASK_SECRET_KEY`
- `UPLOAD_ACCESS_CODE`
- `ADMIN_ACCESS_CODE`
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `GOOGLE_SERVICE_ACCOUNT_JSON`

Never commit these values to GitHub.

## Run locally

```bash
python -m pip install -r requirements.txt
flask --app app run --debug
```

