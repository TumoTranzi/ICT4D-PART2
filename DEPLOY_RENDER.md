# Render + Neon demo deployment

TTsebisa uses SQLite by default when run locally. For the hosted demo, set `TSEBISA_STORAGE_BACKEND=neon` and connect the Neon Postgres database using the private `DATABASE_URL` connection string. This keeps reports, accounts, and conversation messages beyond Render restarts.

## Configure Neon

1. In the Neon project shown in your screenshot, open **Postgres database → Connect**.
2. Select the `production` branch and database, then copy the connection string. Keep it private; it contains the database password.
3. Neon’s dashboard shows this project on its Free plan. Free-plan quotas and availability can change, so check the project’s **Usage** page. Neon says Free projects have a monthly compute allowance and storage limit; the database may suspend while idle.

## Configure Render

1. In Render, open the existing `ttsebisa` web service and choose **Environment**.
2. Add `TSEBISA_STORAGE_BACKEND` with value `neon`.
3. Add `DATABASE_URL` with the Neon connection string. Do not add the connection string to GitHub or paste it into chat.
4. Save and deploy the latest `main` commit. The updated app creates the required tables on its first start.
5. Open the service URL and submit a report. In Neon, open **Postgres database → SQL Editor** and run `SELECT reference, submission_channel, category, status FROM reports ORDER BY created_at DESC;` to see stored reports.

The Render start command seeds eight synthetic dashboard reports and one sample conversation only if those sample references are not already present. They use the placeholder phone `0000000000`; these are demonstration records, not real complaints or contact details.

## Import existing local SQLite data (optional)

The old Render SQLite file lived on temporary service storage and may not be available. If you have a local `tsebisa.db`, set `DATABASE_URL` in a private local `.env`, set `TSEBISA_STORAGE_BACKEND=neon`, and run a dry run first:

```powershell
python migrate_sqlite_to_neon.py
```

If the record counts look right, run:

```powershell
python migrate_sqlite_to_neon.py --apply
```

The migration is additive and skips records that already exist. Back up the SQLite file before importing. Uploaded photos and voice notes remain local files and are not migrated by this script.

## Costs and limits

Neon and Render are separate services with separate free-plan limits. Neon Free currently includes no-cost compute and database storage within its published quotas; exceeding limits or selecting a paid plan may incur charges. This does not make the Render hosting plan paid. [Neon pricing](https://neon.com/pricing)

Render’s free web service may spin down after inactivity, which can delay the next request. The app provides a website and browser USSD simulator, not a carrier short code or outbound SMS.
