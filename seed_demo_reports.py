"""Append a small synthetic dataset for the local dashboard demo.

Safe to rerun: fixed demo references are inserted only when absent, and no existing
reports or conversations outside these sample records are edited. Set TSEBISA_DATA_DIR
to seed another database.
"""
from datetime import datetime
import os
import sqlite3

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.abspath(os.environ.get("TSEBISA_DATA_DIR", PROJECT_DIR))
DB_PATH = os.path.join(DATA_DIR, "tsebisa.db")

DEMO_PHONE = "0000000000"  # Deliberately invalid as a real contact number.
REPORTS = [
    ("TSE-D001", "Website", "water", "Water point leak reported near the market.", "Maseru", "en", "received", "2026-11-18 09:20"),
    ("TSE-D002", "USSD", "roads", "Pothole reported on the road near the school.", "Roma", "st", "in_progress", "2026-10-12 11:05"),
    ("TSE-D003", "Website", "refuse", "Missed refuse collection in the neighbourhood.", "Hlotse", "en", "closed", "2026-09-08 14:30"),
    ("TSE-D004", "USSD", "lights", "Street light is not working near the clinic.", "Mafeteng", "st", "received", "2026-08-21 08:45"),
    ("TSE-D005", "Website", "other", "Community service request for a blocked public area.", "Butha-Buthe", "en", "in_progress", "2026-07-17 16:10"),
    ("TSE-D006", "USSD", "water", "Water supply interruption reported in the area.", "Qacha's Nek", "st", "closed", "2026-06-03 10:00"),
    ("TSE-D007", "Website", "roads", "Road maintenance is needed near the bus stop.", "Thaba-Tseka", "en", "received", "2026-11-05 13:15"),
    ("TSE-D008", "USSD", "refuse", "Refuse collection has been missed this week.", "Mokhotlong", "st", "in_progress", "2026-10-29 12:40"),
]
SAMPLE_MESSAGES = [
    ("citizen", "Citizen", "I am checking how replies appear in this sample conversation.", "2026-11-18 09:22"),
    ("partner", "Minister", "The report has been received and assigned for follow-up.", "2026-11-18 09:25"),
    ("admin", "Prime Minister", "We will review the progress and provide an update.", "2026-11-18 09:27"),
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
    current_description = (collision["description"] or "") if collision else ""
    expected_description = row[3]
    if collision and current_description != expected_description and not current_description.startswith("[DEMO] "):
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
    # Keep the existing sample rows while removing the old visible [DEMO] marker.
    conn.execute(
        "UPDATE reports SET description=?, location=? WHERE reference=?",
        (description, location, reference),
    )
    result = conn.execute(
        """INSERT OR IGNORE INTO reports
        (reference, submission_channel, category, description, location, phone, language, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (reference, channel, category, description, location, DEMO_PHONE, language, status, created_at),
    )
    added += result.rowcount

for role, sender, message, created_at in SAMPLE_MESSAGES:
    old_message = conn.execute(
        "SELECT id, message FROM conversations WHERE report_ref='TSE-D001' AND sender_role=? ORDER BY id LIMIT 1",
        (role,),
    ).fetchone()
    if old_message and old_message["message"].startswith("[DEMO] "):
        conn.execute("UPDATE conversations SET message=? WHERE id=?", (old_message["message"][7:], old_message["id"]))
    conn.execute(
        """INSERT INTO conversations (report_ref, sender_role, sender_name, message, created_at)
        SELECT 'TSE-D001', ?, ?, ?, ?
        WHERE EXISTS (SELECT 1 FROM reports WHERE reference='TSE-D001')
        AND NOT EXISTS (SELECT 1 FROM conversations WHERE report_ref='TSE-D001' AND sender_role=? AND message=?)""",
        (role, sender, message, created_at, role, message),
    )

conn.commit()
total = conn.execute("SELECT COUNT(*) FROM reports").fetchone()[0]
conn.close()
print(f"Added {added} sample reports. Database now has {total} reports.")
print("Sample conversation: reference TSE-D001; phone 0000000000 (placeholder only).")
