# TTsebisa Technical Notes

## Application features

- Flask website for citizen reports in English and Sesotho.
- Browser phone simulator at `/ussd-simulator`; it posts to `POST /api/ussd` and saves confirmed simulator reports to the shared `reports` table.
- Minister and Prime Minister dashboard at `/dashboard`, with report status filters, conversation links, dark KPI cards with six-month sparklines, a monthly column chart with 6/12/all-month selection, and status/category/channel breakdown charts.
- Per-report conversation at `/conversation?reference=TSE-XXXX`. Staff must be signed in. A citizen verifies the generated reference and the phone number recorded on the report; access is limited to that report and the browser session for 30 minutes.
- Messages are stored in the `conversations` SQLite table with report reference, sender role/display name, message and timestamp. Citizen phone numbers are not copied into the message table. Status changes are added to the conversation as system updates.
- The conversation view refreshes messages in the browser every 12 seconds while the page is open. This is polling, not an SMS alert or a live mobile-network chat service.
- Database initialization creates the conversation table and index if missing. It does not drop existing reports or users.

## Data handling and privacy

- Report details and messages are stored in `tsebisa.db`; optional photos and voice notes are stored as files under the configured upload folders.
- Staff report and conversation views require Minister or Prime Minister login. Photo and voice-note routes also require staff login.
- Citizen conversation access requires both the report reference and matching recorded phone number. Keep references private; anyone who has both values can open that report's thread. The current demo does not provide a separate citizen identity account or SMS verification.
- Messages are limited to 1,000 characters. Jinja escapes displayed content; the browser chat refresh uses text nodes rather than inserting raw message HTML.
- No retention/deletion schedule or SMS delivery is implemented. Do not use the free Render filesystem for real or sensitive case data; it is ephemeral. Establish partner-approved retention, durable storage, backup/restore and incident procedures before production use.

## Run

Double-click `start_ttsebisa.bat`, or run `app.py` from this folder after installing `requirements.txt`. The local database is created in the configured data directory.

For a local dashboard demonstration, run `python seed_demo_reports.py` from this folder. It safely adds eight synthetic reports and a sample three-role conversation, and it can be rerun without duplicating them. Sample citizen conversation access: reference `TSE-D001`, phone `0000000000` (placeholder only; not a contact number). These records are written only to the database selected by `TSEBISA_DATA_DIR` (the project-folder database by default).

## Real mobile network and SMS

The project includes a browser USSD simulation only. It does not have a carrier shortcode, a provider callback adapter, or outbound SMS integration. A real service requires an approved provider account, provider API details, public HTTPS callback, SMS credentials, and provider/regulatory costs. Confirm privacy, terms and service ownership before connecting citizens.
