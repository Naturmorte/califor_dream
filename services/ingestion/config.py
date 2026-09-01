"""Source definitions for Phase 1 ingestion.

Field names below were verified against the live Socrata API on 2026-09-01
(sample record fetch), not taken from documentation or search results.
See docs/00-gate0-and-first-milestone.md Section B for the Gate 0 sourcing
decision these are drawn from.
"""

SOCRATA_DOMAIN = "data.sfgov.org"

SOURCES = {
    "building_permits": {
        "source_id": "datasf_building_permits",
        "source_name": "DataSF Building Permits",
        "dataset_id": "i98e-djp9",
        "jurisdiction": "san_francisco_ca",
        "record_type": "building_permit",
        # verified present in live sample record, 2026-09-01
        "id_field": "permit_number",
        "fallback_id_fields": [],
        "date_fields": ["filed_date", "issued_date", "completed_date", "status_date"],
        # best available proxy for "row changed recently" - confirmed present.
        # Not verified to be a true system-maintained watermark; content_hash
        # is the real idempotency guarantee, this field only bounds fetch volume.
        "watermark_field": "last_permit_activity_date",
        "apn_fields": ("block", "lot"),
        "status_field": "status",
        "primary_date_field": "filed_date",
        "creation_event_type": "PERMIT_FILED",
        # (changed field -> derived event type). Order matters: first match wins.
        "event_rules": [
            ("issued_date", "PERMIT_ISSUED"),
            ("completed_date", "PERMIT_COMPLETED"),
            ("status", "PERMIT_STATUS_CHANGED"),
        ],
    },
    "code_violations": {
        "source_id": "datasf_notices_of_violation",
        "source_name": "DataSF Notices of Violation (DBI)",
        "dataset_id": "nbtm-fbw5",
        "jurisdiction": "san_francisco_ca",
        "record_type": "code_violation",
        # NOT complaint_number: live data (2026-09-01) showed a single
        # complaint_number can carry 15-19 distinct line items (one per
        # violated code item), each with its own item_sequence_number.
        # complaint_number is a grouping key, not a row identity - keying on
        # it collapsed 2842 real rows into 983 "duplicates" of the same id.
        "id_field": "item_sequence_number",
        # live data (2026-09-01) showed item_sequence_number is itself null
        # on a real minority of rows (541 of 2842 in one sample window) -
        # not just a sampling fluke. Missing != absent-from-source: these
        # are real records the API returned with that field empty. Falling
        # back to a composite key rather than silently dropping/merging them.
        "fallback_id_fields": ["complaint_number", "code_violation_desc", "block", "lot"],
        "date_fields": ["date_filed"],
        # No confirmed last-activity watermark field exists in this dataset
        # (checked live sample - not present). Incremental sync therefore
        # relies on date_filed as a coarse bound plus full content_hash
        # comparison for correctness, not on a true update watermark.
        "watermark_field": None,
        "apn_fields": ("block", "lot"),
        "status_field": "status",
        "primary_date_field": "date_filed",
        "creation_event_type": "VIOLATION_ITEM_OPENED",
        "event_rules": [
            ("status", "VIOLATION_ITEM_STATUS_CHANGED"),
        ],
    },
    "assessor_roll": {
        "source_id": "datasf_assessor_secured_roll",
        "source_name": "DataSF Assessor Historical Secured Property Tax Rolls",
        "dataset_id": "wv5m-vpq2",
        "jurisdiction": "san_francisco_ca",
        "record_type": "assessor_roll_year",
        # verified via live dataset metadata (data.sfgov.org/api/views/wv5m-vpq2.json)
        # 2026-09-01: this schema has NO sale price field and NO owner name
        # field. Only current_sales_date exists. This corrects the Gate 0
        # assumption in docs/00 that this source gives "sale price + date"
        # ground truth - it only gives sale DATE. assessed_improvement_value
        # + assessed_land_value in the sale year is a *possible* CA Prop-13
        # proxy for price (reassessment to full cash value on change of
        # ownership) but that is a HYPOTHESIS to validate in Gate 1, not a
        # verified price field.
        "id_field": "parcel_number",
        "fallback_id_fields": [],
        "date_fields": ["current_sales_date"],
        # annual snapshot, not an update-log: bound backfill volume by roll
        # year, not by a real update timestamp.
        "watermark_field": "closed_roll_year",
        "snapshot_year_field": "closed_roll_year",
        "apn_fields": ("block", "lot"),
        "status_field": "status_code",
        "primary_date_field": "current_sales_date",
        "creation_event_type": "ASSESSOR_ROLL_FIRST_SEEN",
        # closed_roll_year/row_id mechanically differ every year even when
        # nothing about the property changed - excluded so re-appearing in
        # next year's roll with identical facts registers as unchanged, not
        # as a spurious event (see pipeline.py VOLATILE_FIELDS discussion).
        "extra_hash_excludes": ["closed_roll_year", "row_id", "the_geom"],
        # oldest-year-first per parcel, required for correct diffing (see
        # pipeline.py order_by comment).
        "order_by": "parcel_number,closed_roll_year",
        "event_rules": [
            ("current_sales_date", "PROPERTY_SALE_RECORDED"),
            ("assessed_improvement_value", "ASSESSED_VALUE_CHANGED"),
            ("assessed_land_value", "ASSESSED_VALUE_CHANGED"),
            ("use_code", "USE_CODE_CHANGED"),
            ("number_of_units", "UNIT_COUNT_CHANGED"),
        ],
    },
}
