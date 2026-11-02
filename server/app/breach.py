"""Breach kit (Rule 7). Drafts only: needs lawyer review. We hold hashed principal IDs, so user notices are
produced per principal hash and the customer maps them to contact details in their own systems."""
from datetime import datetime, timedelta, timezone

from dpdp_guard import notices

DISCLAIMER = "DRAFT - not legal advice. Review with counsel before sending or filing."


def board_deadline(detected: datetime) -> datetime:
    return detected + timedelta(hours=72)


def countdown(detected: datetime, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    left = board_deadline(detected) - now
    return {"deadline": board_deadline(detected).isoformat(), "hours_left": round(left.total_seconds() / 3600, 1), "overdue": left.total_seconds() < 0}


def user_notice(business, what, action, advice, contact, lang="en"):
    return notices.render("breach_user", lang, business=business, what=what, action=action, advice=advice, contact=contact)


def board_report(b: dict, business: str) -> str:
    return f"""{DISCLAIMER}

REPORT OF PERSONAL DATA BREACH TO THE DATA PROTECTION BOARD OF INDIA (Rule 7 draft)
Data Fiduciary: {business}
Detected at: {b['detected_at']}   Report due by: {b['board_report_due']}
Title: {b['title']}

1. Nature, extent, timing and location of the breach:
{b['description']}
Data categories involved: {', '.join(b['data_kinds']) or 'TO FILL'}
Data principals affected: {len(b['affected_principals'])}

2. Likely impact on affected data principals: TO FILL
3. Measures taken / proposed to mitigate risk: TO FILL
4. Findings on the person(s) who caused the breach, and remedial steps: TO FILL
5. Notice given to affected data principals: {b['users_notified_at'] or 'NOT YET RECORDED'}
6. Contact for the Board: TO FILL
"""
