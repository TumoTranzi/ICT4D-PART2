"""Append a small, clearly labelled synthetic dataset for the local dashboard demo.

Safe to rerun: fixed demo references are inserted only when absent, and no existing
reports or conversations are edited. Set TSEBISA_DATA_DIR to seed another database.
"""
from datetime import datetime
import os
import sqlite3

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.abspath(os.environ.get("TSEBISA_DATA_DIR", PROJECT_DIR))
DB_PATH = os.path.join(DATA_DIR, "tsebisa.db")

DEMO_PHONE = "0000000000"  # Deliberately invalid as a real contact number.
REPORTS = [
    ("TSE-D001", "Website", "water", "[DEMO] Water point leak reported for dashboard demonstration.", "[DEMO] Maseru", "en", "received", "2026-11-18 09:20"),
    ("TSE-D002", "USSD", "roads", "[DEMO] Pothole report used only to populate the example charts.", "[DEMO] Roma", "st", "in_progress", "2026-10-12 11:05"),
    ("TSE-D003", "Website", "refuse", "[DEMO] Missed refuse collection example report.", "[DEMO] Hlotse", "en", "closed", "2026-09-08 14:30"),
    ("TSE-D004", "USSD", "lights", "[DEMO] Street light fault example; not a real service request.", "[DEMO] Mafeteng", "st", "received", "2026-08-21 08:45"),
    ("TSE-D005", "Website", "other", "[DEMO] General community-service example for the dashboard.", "[DEMO] Butha-Buthe", "en", "in_progress", "2026-07-17 16:10"),
    ("TSE-D006", "USSD", "water", "[DEMO] Water supply example used to demonstrate the USSD channel graph.", "[DEMO] Qacha's Nek", "st", "closed", "2026-06-03 10:00"),
    ("TSE-D007", "Website", "roads", "[DEMO] Road maintenance example; synthetic data only.", "[DEMO] Thaba-Tseka", "en", "received", "2026-11-05 13:15"),
    ("TSE-D008", "USSD", "refuse", "[DEMO] Refuse collection example; synthetic data only.", "[DEMO] Mokhotlong", "st", "in_progress", "2026-10-29 12:40"),
]
SAMPLE_MESSAGES = [
    ("citizen", "Citizen", "[DEMO] I am checking how replies appear in this sample conversation.", "2026-11-18 09:22"),
    ("partner", "Minister", "[DEMO] Sample Minister reply. This is not a real service commitment.", "2026-11-18 09:25"),
    ("admin", "Prime Minister", "[DEMO] Sample Prime Minister reply for demonstration only.", "2026-11-18 09:27"),
]

if not os.path.exists(DB_PATH):
    raise SystemExit(f"Database not found: {DB_PATH}. Start the app once, then rerun this script.")

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
if "reports" not in tables:
    conn.close()
    raise SystemExit("The reports table is missing. Start the app once, then rerun this script.")

for row in REPORTS:
    collision = conn.execute("SELECT description FROM reports WHERE reference=?", (row[0],)).fetchone()
    if collision and not (collision["description"] or "").startswith("[DEMO]"):
        conn.close()
        raise SystemExit(f"Reference {row[0]} is already used by a non-demo report; no demo data was inserted.")

conn.execute("""
    CREATE TABLE IF NOT EXISTS conversations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        report_ref TEXT NOT NULL,
        sender_role TEXT NOT NULL,
        sender_name TEXT NOT NULL,
        message TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (report_ref) REFERENCES reports(reference)
    )
""")
conn.execute("CREATE INDEX IF NOT EXISTS idx_conversations_report_ref ON conversations(report_ref, id)")
existing_before = conn.execute("SELECT COUNT(*) FROM reports").fetchone()[0]
added = 0
for reference, channel, category, description, location, language, status, created_at in REPORTS:
    result = conn.execute(
        """INSERT OR IGNORE INTO reports
        (reference, submission_channel, category, description, location, phone, language, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (reference, channel, category, description, location, DEMO_PHONE, language, status, created_at),
    )
    added += result.rowcount

for role, sender, message, created_at in SAMPLE_MESSAGES:
    conn.execute(
        """INSERT INTO conversations (report_ref, sender_role, sender_name, message, created_at)
        SELECT 'TSE-D001', ?, ?, ?, ?
        WHERE EXISTS (SELECT 1 FROM reports WHERE reference='TSE-D001')
        AND NOT EXISTS (SELECT 1 FROM conversations WHERE report_ref='TSE-D001' AND sender_role=? AND message=?)""",
        (role, sender, message, created_at, role, message),
    )

conn.commit()
total = conn.execute("SELECT COUNT(*) FROM reports").fetchone()[0]
demo_total = conn.execute("SELECT COUNT(*) FROM reports WHERE description LIKE '[DEMO]%' ").fetchone()[0]
conn.close()
print(f"Added {added} demo reports. Database now has {total} reports, including {demo_total} labelled demo reports.")
print("Demo conversation: reference TSE-D001; phone 0000000000 (demo placeholder only).")
