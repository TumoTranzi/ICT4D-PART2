# TTsebisa

A fresh, runnable Tsebisa project with the website, shared SQLite report database, administration dashboard, and browser-based feature-phone USSD simulator.

## Run on Windows

1. Install Python 3.10 or later.
2. Double-click `start_ttsebisa.bat` (or run it from PowerShell).
3. Open http://127.0.0.1:5001/

The launcher creates a local `.venv`, installs `requirements.txt`, and starts Flask. The app creates a fresh `tsebisa.db` on first start; this project does not include or overwrite the database from the original Tsebisa folder.

## Use the phone simulator

Select **Phone** in the left navigation. Press `*123#`, choose **OK**, and follow the prompts. Confirming a report saves it to the same database used by the website and dashboard. Reports are labeled `USSD`.

## Included features

- Sesotho and English website reporting
- Browser-based phone keypad and USSD conversation
- Shared SQLite reports for website and simulator submissions
- Dashboard with channel labels and status updates
- Safe database initialization; startup does not drop existing tables

## Demo vs. live mobile service

The Phone page simulates USSD in the browser. A real carrier USSD code, network gateway, public HTTPS callback, and SMS provider are not included because those require a provider account and approved service. The app does not send SMS yet.

## Public hosting

See [DEPLOYMENT.md](DEPLOYMENT.md) for the three-week demo deployment notes. Production mode requires a private `.env` with a fresh secret key and admin password. Do not upload a local database, voice notes, photos, or `.venv` to a public code repository.
