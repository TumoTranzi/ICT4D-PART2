# TTsebisa Technical Notes

## Local pilot features

- Flask website for citizen reports in English and Sesotho.
- Browser phone simulator at `/ussd-simulator`, linked as **Phone** in the left navigation.
- Simulator sends accumulated menu input to `POST /api/ussd`. The callback returns plain-text `CON` or `END` replies and saves a report after confirmation.
- Website and simulator reports use the same `tsebisa.db` and `reports` table. The dashboard displays the submission channel.
- Database initialization creates missing tables and adds `submission_channel` to an older `reports` table; startup does not drop tables.

## Run

Double-click `start_ttsebisa.bat`, or run `app.py` from this folder after installing `requirements.txt`. The default port is 5001. The database is created in this project folder on first start.

## Real mobile network and SMS

This project includes a browser simulation only. It does not have a carrier shortcode, provider callback adapter, or outbound SMS integration. A real deployment needs an approved provider account, their API specification, a public HTTPS callback, and SMS credentials. Confirm provider support and fees before selecting an adapter.

## Pilot security

The dashboard has no login, and Flask's development server is for local demonstrations only. Add authentication, a production WSGI server, HTTPS, secure environment-based secrets, and retention/backups before deployment with real citizens.
