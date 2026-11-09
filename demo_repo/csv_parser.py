"""
A tiny CSV utility used by the demo project.

Known bug (see ISSUE.md): parse_row() crashes when the 'date' column
is an empty string, because datetime.strptime cannot parse "".
"""
from datetime import datetime


def parse_row(row: dict) -> dict:
    """Parse a single CSV row (as a dict) into typed fields.

    Expected keys: 'name', 'amount', 'date' (format: YYYY-MM-DD).
    """
    name = row.get("name", "").strip()
    amount = float(row.get("amount", 0) or 0)

    # BUG: this blows up with ValueError when row["date"] == ""
    date_str = row.get("date", "")
    date = datetime.strptime(date_str, "%Y-%m-%d")

    return {"name": name, "amount": amount, "date": date}


def parse_rows(rows: list) -> list:
    """Parse a list of raw CSV row dicts."""
    return [parse_row(row) for row in rows]
