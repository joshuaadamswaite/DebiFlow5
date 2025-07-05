from flask import render_template, request, redirect, flash
import pandas as pd
from google.cloud import storage
import io
from datetime import datetime
from scripts.utils import build_investor_path, require_investor

def payment_summary(bucket_name, investor):
    report_date = request.args.get("report_date")
    if not report_date:
        flash("❌ No report date provided.")
        return redirect("/")

    gcs = storage.Client()
    bucket = gcs.bucket(bucket_name)

    # Load Receivables_Allocated, disable low-memory parser to avoid DtypeWarning
    recv_blob = bucket.blob(
    build_investor_path(investor, "outputs", f"Receivables_Allocated_{report_date}.csv")
)

    df_recv = pd.read_csv(
        io.StringIO(recv_blob.download_as_text()),
        dtype=str,            # or {'LoanID': str, 'Minimum_Recovery_Amount': float, ...}
        low_memory=False
    )

    # Load HP_Repayments_Master similarly
    repay_blob = bucket.blob(
    build_investor_path(investor, "master", f"HP_Repayments_Master_{report_date}.csv")
)
    df_repay = pd.read_csv(
        io.StringIO(repay_blob.download_as_text()),
        dtype=str,
        low_memory=False
    )

    # Clean Repurchase_Date
    df_recv["Repurchase_Date"] = (
        pd.to_datetime(df_recv["Repurchase_Date"], errors="coerce")
          .dt.strftime("%Y%m%d")
    )

    # Convert numeric columns back if needed
    df_recv["Minimum_Recovery_Amount"] = pd.to_numeric(df_recv["Minimum_Recovery_Amount"], errors="coerce").fillna(0)
    df_repay["HP_Repayment_Amount"] = pd.to_numeric(df_repay["HP_Repayment_Amount"], errors="coerce").fillna(0)

    # Sums and counts
    receivables_sum   = df_recv["Minimum_Recovery_Amount"].sum()
    repayments_sum    = df_repay["HP_Repayment_Amount"].sum()
    total_due         = receivables_sum - repayments_sum

    repurchased_df    = df_recv[df_recv["Repurchase_Date"] == report_date]
    total_repurchased = repurchased_df["Minimum_Recovery_Amount"].sum()
    num_repurchased   = repurchased_df["LoanID"].nunique()

    total_repaid      = max(0, total_due - total_repurchased)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    return render_template(
        "payment_summary.html",
        report_date=report_date,
        timestamp=timestamp,
        total_due=total_due,
        total_repaid=total_repaid,
        total_repurchased=total_repurchased,
        num_repurchased=num_repurchased,
        investor=investor
    )
