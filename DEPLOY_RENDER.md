# Publish TTsebisa on Render

This deploys TTsebisa as a separate service. It does not alter the existing PythonAnywhere app.

## What this deployment needs

- A **private GitHub repository** containing the clean TTsebisa project.
- A Render account connected to that repository.
- Render's smallest paid web service and a 1 GB persistent disk. The current listed price is $7/month for compute plus $0.25/GB-month for the disk, prorated while active. A three-week demo is approximately $5.10 before tax or any extra bandwidth. Check the final amount shown by Render before creating the service.

The persistent disk keeps the SQLite database, photos and voice notes through restarts and deploys. Do not use a free Render web service for this app's SQLite data: its local files are temporary and can be deleted on spin-down, restart or deploy.

## Prepare a private repository

Create an empty **private** repository on GitHub, then upload the project files from this folder. Exclude:

- `.venv/`
- `tsebisa.db`
- `.env`
- `static/voice_notes/`
- `static/report_photos/`
- `__pycache__/`

The existing `.gitignore` already excludes these items. Do not make the repository public: deployment source is private, and the database and media contain demo submissions.

## Create the Render service

1. In Render, choose **New → Blueprint** and connect the private GitHub repository.
2. Render reads `render.yaml` and prepares the web service and persistent disk.
3. When prompted, enter a strong, unique value for `TSEBISA_ADMIN_PASSWORD`. Render generates the Flask secret key.
4. Review the service plan and disk price in Render, then create the service.
5. Once deployment is live, open the `onrender.com` URL shown on the service page. The browser USSD demo is at `/ussd-simulator`; staff sign in at `/login` with username `admin` and the password entered during setup.

The first production startup creates a clean database on the persistent disk and seeds the administrator account. It does not copy local demo reports or upload files.

## Three-week demo closeout

Download a backup of `/var/data` before deleting the service. Deleting the service or its disk removes the hosted database and uploads. Stop or delete the paid service when the demo ends to avoid continued charges.

This provides the website and browser-based USSD simulator over the internet. It does not provision a mobile carrier short code or activate outbound SMS; those require a separate gateway/provider account.
