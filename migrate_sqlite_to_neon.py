"""Copy a local TTsebisa SQLite database into the configured Neon database.

Dry-run by default. Set DATABASE_URL and TSEBISA_STORAGE_BACKEND=neon, then use
--apply to perform an idempotent import. Existing records are left untouched.
"""
import argparse
import os
import sqlite3

from storage import create_store

store = create_store("neon", "", os.environ.get("DATABASE_URL"))
store.initialize()


def rows(conn, table):
    return [dict(row) for row in conn.execute(f"SELECT * FROM {table}").fetchall()]


def migrate(source_path, apply_changes=False):
    if not os.path.isfile(source_path):
        raise FileNotFoundError(f"SQLite file not found: {source_path}")
    source = sqlite3.connect(source_path)
    source.row_factory = sqlite3.Row
    try:
        tables = {row[0] for row in source.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        reports = rows(source, "reports") if "reports" in tables else []
        users = rows(source, "users") if "users" in tables else []
        messages = rows(source, "conversations") if "conversations" in tables else []
    finally:
        source.close()

    new_reports = [row for row in reports if not store.get_report(row["reference"])]
    new_users = [row for row in users if not store.get_user(row["username"])]
    current_messages = store.list_messages()
    existing_messages = {(m.get("report_ref"), m.get("sender_role"), m.get("sender_name"), m.get("message"), m.get("created_at")) for m in current_messages}
    new_messages = [m for m in messages if (m.get("report_ref"), m.get("sender_role"), m.get("sender_name"), m.get("message"), m.get("created_at")) not in existing_messages]

    print(f"SQLite source: {os.path.abspath(source_path)}")
    print(f"Records to import: {len(new_reports)} reports, {len(new_users)} accounts, {len(new_messages)} messages.")
    if not apply_changes:
        print("Dry run only. Add --apply to write these records to Neon.")
        return

    for row in new_reports:
        row.pop("id", None)
        if not store.create_report(row):
            raise RuntimeError(f"Report reference already exists during import: {row['reference']}")
    for row in new_users:
        row.pop("id", None)
        from storage import DuplicateUserError
        try:
            store.create_user(row)
        except DuplicateUserError:
            pass
    for message in new_messages:
        store.add_message({key: message.get(key) for key in
                           ("report_ref", "sender_role", "sender_name", "message", "created_at")})
    print("Import completed. Existing records were not overwritten.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=os.path.join(os.path.dirname(__file__), "tsebisa.db"))
    parser.add_argument("--apply", action="store_true", help="perform the migration; default is a dry run")
    args = parser.parse_args()
    migrate(args.source, args.apply)
