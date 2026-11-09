Title: CSV upload fails when a row contains an empty date

Body:
When uploading a CSV file where some rows have an empty "date" column,
the parser crashes with:

    ValueError: time data '' does not match format '%Y-%m-%d'

Expected: rows with an empty date should be parsed with date = None
instead of crashing the whole upload.

Steps to reproduce:
1. Prepare a CSV with a row where the date column is blank.
2. Call csv_parser.parse_rows() on the parsed rows.
3. Observe the ValueError.
