import pandas as pd

def validate_file(file_name: str, df: pd.DataFrame) -> list:
    """
    Validates the uploaded file based on filename and content rules.
    Returns a list of grouped error strings with limited examples.
    """
    errors = []

    # If this is a CustomerDetails file, skip validation
    if file_name.startswith("CustomerDetails"):
        return errors

    # Extract expected date from filename (for Payments only)
    date_part = file_name.split("_")[-1].replace(".csv", "")
    if len(date_part) != 8:
        errors.append("Filename does not end with YYYYMMDD date.")
        return errors
    expected_date = f"{date_part[:4]}-{date_part[4:6]}-{date_part[6:]}"

    schemas = {
        "HP_Repayments": {
            "columns": ["HP_Repayment_Date","BankStatement_Ref","HP_Repayment_Amount","To"],
            "date_columns": ["HP_Repayment_Date"],
            "match_date_column": None
        },
        "Payments": {
            "columns": ["LoanID","Paid_Date","Amount_Paid"],
            "date_columns": ["Paid_Date"],
            "match_date_column": "Paid_Date"
        },
        "Schedule": {
            "columns": [
                "LoanID","Purchase_Date","Due_Date","Advance_Rate",
                "Receivable_Outstandings","Purchase_Consideration","entity"
            ],
            "date_columns": ["Purchase_Date","Due_Date"],
            "match_date_column": None
        }
    }

    file_type = next((prefix for prefix in schemas if file_name.startswith(prefix)), None)
    if not file_type:
        errors.append("Unknown file type.")
        return errors

    schema = schemas[file_type]

    # Normalize headers
    df.columns = [c.strip().lstrip("\ufeff") for c in df.columns]

    if df.columns.tolist() != schema["columns"]:
        errors.append(
            "Column headers do not match expected format.\n"
            f" Expected: {schema['columns']}\n"
            f" Actual:   {df.columns.tolist()}"
        )
        return errors

    if df.empty:
        errors.append("Warning: file contains no rows.")
        return errors

    # Date-format checks
    for col in schema["date_columns"]:
        parsed = pd.to_datetime(df[col], errors="coerce", format="%Y-%m-%d")
        invalid_rows = parsed.isnull()
        if invalid_rows.any():
            idxs = invalid_rows[invalid_rows].index
            total = len(idxs)
            examples = "\n".join(
                [f"  Row {i+2}: value = '{df.at[i, col]}'" for i in idxs[:5]]
            )
            more = f"...and {total-5} more similar errors." if total > 5 else ""
            errors.append(
                f"Invalid date format in {col}: {total} errors found.\nExamples:\n{examples}\n{more}"
            )

    # Filename-vs-column-date matching (Payments only)
    if schema["match_date_column"]:
        col = schema["match_date_column"]
        mismatch = df[col].astype(str).str[:10] != expected_date
        if mismatch.any():
            idxs = mismatch[mismatch].index
            total = len(idxs)
            examples = "\n".join(
                [f"  Row {i+2}: value = '{df.at[i, col]}'" for i in idxs[:5]]
            )
            more = f"...and {total-5} more similar errors." if total > 5 else ""
            errors.append(
                f"{col} does not match filename date {expected_date}: {total} rows.\nExamples:\n{examples}\n{more}"
            )

    # Schedule-specific: Due_Date >= Purchase_Date
    if file_type == "Schedule":
        pds = pd.to_datetime(df["Purchase_Date"], errors="coerce", format="%Y-%m-%d")
        dds = pd.to_datetime(df["Due_Date"], errors="coerce", format="%Y-%m-%d")
        invalid = dds < pds
        if invalid.any():
            idxs = invalid[invalid].index
            total = len(idxs)
            examples = "\n".join(
                [f"  Row {i+2}: Purchase_Date='{df.at[i, 'Purchase_Date']}', Due_Date='{df.at[i, 'Due_Date']}'" for i in idxs[:5]]
            )
            more = f"...and {total-5} more similar errors." if total > 5 else ""
            errors.append(
                f"Due_Date earlier than Purchase_Date in {total} rows.\nExamples:\n{examples}\n{more}"
            )

    return errors
