"""Insert the small synthetic dashboard dataset without overwriting real records."""
from app import store

DEMO_PHONE = "0000000000"  # Invalid placeholder; never a real contact.
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


def seed():
    added = 0
    for reference, channel, category, description, location, language, status, created_at in REPORTS:
        existing = store.get_report(reference)
        if existing:
            current_description = (existing.get("description") or "").removeprefix("[DEMO] ")
            if current_description != description:
                raise RuntimeError(f"Reference {reference} is already used by another report; no demo data was added.")
            continue
        added += bool(store.create_report({
            "reference": reference, "submission_channel": channel, "category": category,
            "description": description, "location": location, "phone": DEMO_PHONE,
            "language": language, "status": status, "created_at": created_at,
            "voice_note": None, "photo": None,
        }))

    old_messages = store.list_messages("TSE-D001")
    existing_messages = {(m.get("sender_role"), m.get("message")) for m in old_messages}
    for role, sender, message, created_at in SAMPLE_MESSAGES:
        if (role, message) not in existing_messages:
            store.add_message({"report_ref": "TSE-D001", "sender_role": role,
                               "sender_name": sender, "message": message,
                               "created_at": created_at})
    print(f"Added {added} sample reports. Database now has {store.count_reports()} reports.")
    print("Sample conversation: reference TSE-D001; phone 0000000000 (placeholder only).")


if __name__ == "__main__":
    seed()
