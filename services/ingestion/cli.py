import argparse
import json
import sys

from services.ingestion import db
from services.ingestion.config import SOURCES
from services.ingestion.pipeline import ingest_source


def cmd_ingest(args):
    conn = db.connect()
    db.init_schema(conn)
    result = ingest_source(
        conn, args.source, since=args.since, max_records=args.limit
    )
    print(json.dumps(result, indent=2))


def cmd_changes(args):
    conn = db.connect()
    cur = conn.execute(
        "SELECT event_type, previous_value, new_value, effective_at, "
        "detected_at, source, confidence FROM event WHERE entity_id=? "
        "ORDER BY detected_at",
        (args.apn,),
    )
    rows = cur.fetchall()
    if not rows:
        print(f"No events found for entity_id={args.apn}")
        return
    for r in rows:
        print(json.dumps({
            "event_type": r[0],
            "previous_value": r[1],
            "new_value": r[2],
            "effective_at": r[3],
            "detected_at": r[4],
            "source": r[5],
            "confidence": r[6],
        }, indent=2))


def cmd_stats(args):
    conn = db.connect()
    print("Sources:", list(SOURCES.keys()))
    for table in ("raw_record", "event", "ingestion_job"):
        try:
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        except Exception as e:
            count = f"error: {e}"
        print(f"{table}: {count}")


def main():
    parser = argparse.ArgumentParser(description="Phase 1 ingestion CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_ingest = sub.add_parser("ingest", help="Run ingestion for one source")
    p_ingest.add_argument("--source", required=True, choices=list(SOURCES.keys()))
    p_ingest.add_argument("--since", default=None, help="ISO date/time lower bound")
    p_ingest.add_argument("--limit", type=int, default=None, help="Max records to fetch")
    p_ingest.set_defaults(func=cmd_ingest)

    p_changes = sub.add_parser("changes", help="Show event history for an entity (apn)")
    p_changes.add_argument("--apn", required=True)
    p_changes.set_defaults(func=cmd_changes)

    p_stats = sub.add_parser("stats", help="Show row counts")
    p_stats.set_defaults(func=cmd_stats)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    sys.exit(main())
