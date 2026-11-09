from csv_parser import parse_row, parse_rows


def test_parse_row_with_valid_date():
    row = {"name": "Alice", "amount": "100", "date": "2024-01-15"}
    result = parse_row(row)
    assert result["name"] == "Alice"
    assert result["amount"] == 100.0
    assert result["date"].year == 2024


def test_parse_row_with_empty_date():
    """This is the case from the reported issue: empty date should not crash."""
    row = {"name": "Bob", "amount": "50", "date": ""}
    result = parse_row(row)
    assert result["name"] == "Bob"
    assert result["date"] is None


def test_parse_rows_mixed():
    rows = [
        {"name": "Alice", "amount": "10", "date": "2024-02-01"},
        {"name": "Bob", "amount": "20", "date": ""},
    ]
    parsed = parse_rows(rows)
    assert parsed[0]["date"].month == 2
    assert parsed[1]["date"] is None
