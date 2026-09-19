# DAAC Photo Organizer

Automatically sorts photos uploaded through the DAAC Jotform into the correct 2026 Google Drive category folder.

## Routing

- Open Houses
- Community Events
- Environmental & Community Projects
- Outreach & Partnerships
- Social Media
- Other / Needs Sorting

## How it works

A scheduled GitHub Actions workflow reads recent submissions from Jotform, matches each submission's uploaded photo filenames to files in the Google Drive intake folder, and moves each file to the configured category folder. Successfully processed Jotform submission IDs are recorded in `state/processed.json` so reruns are safe.

## Required GitHub Actions secrets

- `JOTFORM_API_KEY` — Jotform API key with permission to read submissions.
- `GOOGLE_SERVICE_ACCOUNT_JSON` — complete Google service-account JSON credential. The service account must have Editor access to the DAAC Photo Upload inbox and destination folders (or their shared parent folder).

Never commit either credential to this repository.

## Manual test

After the two secrets are configured, open **Actions → DAAC Photo Organizer → Run workflow**. The workflow also runs automatically every 5 minutes.
