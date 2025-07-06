import os
from flask import Flask, render_template, request, redirect, flash, session
from google.cloud import storage
from datetime import datetime
from scripts.file_tracker import get_reporting_dates

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), "scripts"))

import scripts.output_generators  # This is your script with the function

from scripts.payment_summary import payment_summary
from scripts.download_confirmation import download_confirmation
from flask import url_for

from scripts.utilisation_request import generate_utilisation_request

from io import StringIO
import pandas as pd
from scripts.validate_uploads import validate_file

from flask import send_file, request, redirect, flash

from scripts.utils import build_investor_path, require_investor

# Config
ALLOWED_PREFIXES = ['HP_Repayments_', 'CustomerDetails_', 'Schedule_', 'Payments_']
GCS_BUCKET = os.getenv("GCS_BUCKET", "debiflow-staging")

app = Flask(__name__)
app.secret_key = os.urandom(24)

def allowed_file(filename):
    return filename.endswith('.csv') and any(filename.startswith(prefix) for prefix in ALLOWED_PREFIXES)


@app.route("/", methods=["GET"])
def landing_page():
    from google.cloud import storage

    client = storage.Client()
    bucket = client.bucket(GCS_BUCKET)

    # List all folders under Investors/
    iterator = bucket.list_blobs(prefix="Investors/", delimiter="/")
    prefixes = set()

    # This forces iteration and fills prefixes
    for page in iterator.pages:
        prefixes.update(page.prefixes)

    # Clean investor names (remove "Investors/" and trailing "/")
    investors = [p.replace("Investors/", "").strip("/") for p in sorted(prefixes)]

    return render_template("landing.html", investors=investors)


@app.route("/upload", methods=["GET", "POST"])
@require_investor
def upload_routes(investor):
    from google.cloud import storage
    import re
    from collections import defaultdict
    from io import StringIO
    import pandas as pd

    client = storage.Client()
    bucket = client.bucket(GCS_BUCKET)

    if request.method == "POST":
        files = request.files.getlist("files[]")
        if not files or all(f.filename == "" for f in files):
            flash("❌ No files selected.")
            return redirect(url_for("upload_routes", investor=investor))

        errors = []
        warnings = []

        # Validate each file
        for f in files:
            fn = f.filename
            if not allowed_file(fn):
                errors.append(f"{fn}: Invalid filename prefix.")
                continue

            try:
                f.stream.seek(0)
                df = pd.read_csv(StringIO(f.stream.read().decode("utf-8")), dtype=str)
            except Exception as e:
                errors.append(f"{fn}: Could not parse CSV ({e}).")
                continue

            for err in validate_file(fn, df):
                if err.startswith("Warning"):
                    warnings.append(f"{fn}: {err}")
                else:
                    errors.append(f"{fn}: {err}")

        # If any hard errors, abort with filenames only
        #if errors:
        #    bad = sorted({e.split(":", 1)[0] for e in errors})
        #    flash(f"❌ Upload failed. Issue in file{'s' if len(bad)>1 else ''}: {', '.join(bad)}.")
        #    return redirect(url_for("upload_routes", investor=investor))
        
        if errors:
            bad = sorted({e.split(":", 1)[0] for e in errors})
            flash(f"❌ Upload failed. Issue in file{'s' if len(bad)>1 else ''}: {', '.join(bad)}.")
            # Show the errors in the same page without redirecting
            blobs = bucket.list_blobs(prefix=f"Investors/{investor}/raw/")
            REQUIRED_PREFIXES = {"Schedule_", "CustomerDetails_", "Payments_", "HP_Repayments_"}
            raw_dates = defaultdict(set)
            for blob in blobs:
                name = blob.name.split("/")[-1]
                for prefix in REQUIRED_PREFIXES:
                    m = re.match(rf"^{prefix}(\d{{8}})\.csv$", name)
                    if m:
                        raw_dates[m.group(1)].add(prefix)
            complete_dates = sorted(
                [d for d, ps in raw_dates.items() if ps == REQUIRED_PREFIXES],
                reverse=True
            )
            return render_template(
                "upload.html",
                available_dates=complete_dates,
                investor=investor,
                errors=errors
            )


        # If any warnings, show filenames only (but continue)
        if warnings:
            warn = sorted({w.split(":", 1)[0] for w in warnings})
            flash(f"⚠️ Uploaded with formatting warnings in: {', '.join(warn)}. Please check those files.")

        # All good – upload each file
        for f in files:
            f.stream.seek(0)
            bucket.blob(build_investor_path(investor, "raw",f.filename)) \
                  .upload_from_file(f.stream, content_type="text/csv")

        # Single success message
        count = len(files)
        flash(f"✅ Successfully uploaded {count} file{'s' if count>1 else ''}!")
        return redirect(url_for("upload_routes", investor=investor))

    # === GET logic unchanged ===
    blobs = bucket.list_blobs(prefix=f"Investors/{investor}/raw/")
    REQUIRED_PREFIXES = {"Schedule_", "CustomerDetails_", "Payments_", "HP_Repayments_"}
    raw_dates = defaultdict(set)
    for blob in blobs:
        name = blob.name.split("/")[-1]
        for prefix in REQUIRED_PREFIXES:
            m = re.match(rf"^{prefix}(\d{{8}})\.csv$", name)
            if m:
                raw_dates[m.group(1)].add(prefix)
    complete_dates = sorted(
        [d for d, ps in raw_dates.items() if ps == REQUIRED_PREFIXES],
        reverse=True
    )
    return render_template("upload.html", available_dates=complete_dates, investor=investor)






@app.route("/pending", methods=["POST"])
@require_investor
def pending_confirmations(investor):
    from datetime import datetime
    report_date = request.form.get("report_date")
    if not report_date:
        flash("❌ No report date provided.")
        return redirect(url_for("upload_routes", investor=investor))


    latest, previous = get_reporting_dates(reference_date=report_date, investor=investor)
    if not previous:
        flash("❌ No previous master reporting period found.")
        return redirect(url_for("upload_routes", investor=investor))


    def format_date(yyyymmdd):
        return datetime.strptime(yyyymmdd, "%Y%m%d").strftime("%Y-%m-%d")

    reporting_period = format_date(report_date)

    master_files = [
        f"Schedule_Master_{previous}.csv",
        f"CustomerDetails_Master_{previous}.csv",
        f"Payments_Master_{previous}.csv",
        f"HP_Repayments_Master_{previous}.csv"
    ]

    return render_template(
        "pending.html",
        reporting_period=reporting_period,
        master_files=master_files,
        report_date=report_date,
        investor=investor
    )




@app.route("/confirm", methods=["POST"])
@require_investor
def confirm_and_merge(investor):
    import pandas as pd
    from io import BytesIO
    from datetime import datetime
    from scripts.file_tracker import get_reporting_dates
    from scripts.receivables_allocated import generate_receivables_allocated
    import scripts.output_generators

    # Use the date selected by the user
    report_date = request.form.get("report_date")
    if not report_date:
        flash("❌ No report date provided.")
        return redirect(url_for("pending_confirmations", investor=investor))

    # Determine previous reporting date dynamically
    latest, previous = get_reporting_dates(reference_date=report_date, investor=investor)
    if not previous:
        flash("❌ No previous master reporting period found.")
        return redirect(url_for("pending_confirmations", investor=investor))

    print(f"\n📦 Confirming merge for report_date={report_date}, previous={previous}")

    client = storage.Client()
    bucket = client.bucket(GCS_BUCKET)

    prefixes = ["Schedule_", "CustomerDetails_", "Payments_", "HP_Repayments_"]
    updated_files = []

    for prefix in prefixes:
        try:
            raw_name = f"{prefix}{report_date}.csv"
            master_prev_name = f"{prefix}Master_{previous}.csv"
            master_new_name = f"{prefix}Master_{report_date}.csv"

            print(f"\n🔄 Merging {raw_name} + {master_prev_name} → {master_new_name}")

            # Prefetch bytes
            blob_prev = bucket.blob(build_investor_path(investor, "master",master_prev_name))
            blob_new = bucket.blob(build_investor_path(investor, "raw",raw_name))
            prev_bytes = blob_prev.download_as_bytes()
            new_bytes = blob_new.download_as_bytes()

            # Load all columns as string for fast read
            df_prev = pd.read_csv(BytesIO(prev_bytes), dtype=str, low_memory=False)
            df_new = pd.read_csv(BytesIO(new_bytes), dtype=str, low_memory=False)

            # Clean columns
            df_prev.columns = df_prev.columns.str.strip()
            df_new.columns = df_new.columns.str.strip()

            print(f"✅ Loaded previous: {master_prev_name} ({len(df_prev)} rows)")
            print(f"✅ Loaded new raw: {raw_name} ({len(df_new)} rows)")
            print(f"🧾 Columns in {raw_name}: {df_new.columns.tolist()}")

            # Convert date columns if present
            for date_col in ["Purchase_Date", "Due_Date", "Paid_Date"]:
                for df in [df_prev, df_new]:
                    if date_col in df.columns:
                        df[date_col] = pd.to_datetime(df[date_col], errors="coerce").dt.normalize()

            # Example numeric columns (adjust if needed)
            numeric_cols = ["Amount", "SomeOtherNumeric"]
            for df in [df_prev, df_new]:
                for col in numeric_cols:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors="coerce")

            # Drop fully blank rows
            df_prev = df_prev.dropna(how="all")
            df_new = df_new.dropna(how="all")

            # Drop missing LoanIDs if Schedule_
            if prefix.startswith("Schedule_") and "LoanID" in df_new.columns:
                df_prev = df_prev[df_prev["LoanID"].notna()]
                df_new = df_new[df_new["LoanID"].notna()]

            # Ensure same column order
            df_prev = df_prev[df_new.columns.tolist()]

            # Combine dataframes
            df_combined = pd.concat([df_prev, df_new], ignore_index=True)

            # Upload combined master file
            output = BytesIO()
            df_combined.to_csv(output, index=False)
            output.seek(0)
            bucket.blob(build_investor_path(investor, "master",master_new_name)).upload_from_file(output, content_type="text/csv")
            print(f"☁️ Uploaded: {master_new_name} ({len(df_combined)} rows)")

            updated_files.append(master_new_name)

        except Exception as e:
            print(f"❌ Error processing {prefix}: {e}")
            flash(f"❌ Failed to merge {prefix}: {str(e)}")
            return redirect(url_for("pending_confirmations", investor=investor))


    # Check that all required masters exist before proceeding
    required_files = [
        build_investor_path(investor, "master", f"Schedule_Master_{report_date}.csv"),
        build_investor_path(investor, "master", f"Payments_Master_{report_date}.csv"),
        build_investor_path(investor, "master", f"HP_Repayments_Master_{report_date}.csv")
    ]
    missing_files = [f for f in required_files if not bucket.blob(f).exists()]
    if missing_files:
        print("❌ Missing required files:", missing_files)
        flash("❌ Missing required files for output generation:\n" + ", ".join(missing_files))
        return redirect(url_for("pending_confirmations", investor=investor))


    # Run allocation steps
    try:
        scripts.output_generators.generate_payments_allocated(report_date=report_date, bucket=GCS_BUCKET, investor=investor)
        print(f"✅ Payments_Allocated_{report_date}.csv generated")
        flash(f"✅ Payments_Allocated_{report_date}.csv generated")
    except Exception as e:
        print(f"❌ Error generating Payments_Allocated: {e}")
        flash(f"⚠️ Failed to generate Payments_Allocated: {str(e)}")

    try:
        generate_receivables_allocated(report_date=report_date, bucket=GCS_BUCKET, prior_report_date=previous, investor=investor)
        print(f"✅ Receivables_Allocated_{report_date}.csv generated")
        flash(f"✅ Receivables_Allocated_{report_date}.csv generated")
    except Exception as e:
        print(f"❌ Error generating Receivables_Allocated: {e}")
        flash(f"⚠️ Failed to generate Receivables_Allocated: {str(e)}")

    print(f"\n✅ All files merged and outputs generated for {report_date}: {updated_files}\n")
    flash(f"✅ Master file merges complete for {report_date}: " + ", ".join(updated_files))
    return redirect(url_for("summary", report_date=report_date, investor=investor))






import pandas as pd
import os
from scripts.summary_generator import generate_summary_outputs

@app.route('/summary', methods=["GET", "POST"])
@require_investor
def summary(investor):
    from scripts.file_tracker import get_reporting_dates
    
    # Step 1: Try to get from query string
    report_date = request.args.get("report_date") or request.form.get("report_date")
        # right after grabbing GET/POST inputs:
    incoming_get  = request.args.get("report_date")
    incoming_post = request.form.get("report_date")
    print(f"[DEBUG] incoming GET report_date  = {incoming_get!r}")
    print(f"[DEBUG] incoming POST report_date = {incoming_post!r}")

    # after you do report_date = incoming_get or incoming_post:
    print(f"[DEBUG] initial report_date        = {report_date!r}")

    # inside your fallback block, before and after calling get_reporting_dates:
    dates_tuple = get_reporting_dates(reference_date=report_date, investor=investor)
    print(f"[DEBUG] get_reporting_dates({report_date!r}) → {dates_tuple!r} (investor={investor})")
    report_date = max(dates_tuple) if dates_tuple else None
    print(f"[DEBUG] fallback report_date       = {report_date!r}")

    # before loading each blob:
    print(f"[DEBUG] Loading outputs/Receivables_Allocated_{report_date}.csv")
    print(f"[DEBUG] Loading master/HP_Repayments_Master_{report_date}.csv")

    # Step 2: Fallback to latest date in GCS if missing
    if not report_date:
        reporting_dates = get_reporting_dates(reference_date=report_date, investor=investor)
        report_date = max(reporting_dates) if reporting_dates else None

    # Step 3: Abort if still missing
    if not report_date:
        flash("❗ Could not determine a reporting date. Please upload or confirm files.")
        return redirect(url_for("upload_routes", investor=investor))

    # Use session to remember threshold across redirects
    if request.method == "POST":
        try:
            threshold = int(request.form.get("dpd_threshold", "999"))
        except ValueError:
            threshold = 999
        session['dpd_threshold'] = threshold
    else:
        threshold = session.get('dpd_threshold', 999)

    # Load from GCS
    from google.cloud import storage
    import io
    client = storage.Client()
    bucket = client.bucket(GCS_BUCKET)

    # === Receivables Allocated ===
    recv_blob = bucket.blob(build_investor_path(investor, "outputs", f"Receivables_Allocated_{report_date}.csv"))
    df_recv = pd.read_csv(io.StringIO(recv_blob.download_as_text()), dtype={"LoanID": str}, low_memory=False)
    # Force clean dates/numeric
    df_recv['Due_Date'] = pd.to_datetime(df_recv['Due_Date'], errors='coerce').dt.normalize()
    df_recv['Repurchase_Date'] = pd.to_datetime(df_recv['Repurchase_Date'], errors='coerce').dt.normalize()
    df_recv['Days_Past_Due'] = pd.to_numeric(df_recv['Days_Past_Due'], errors='coerce')
    if 'Minimum_Recovery_Amount' in df_recv.columns:
        df_recv['Minimum_Recovery_Amount'] = pd.to_numeric(df_recv['Minimum_Recovery_Amount'], errors='coerce')

    # === HP Repayments Master ===
    repay_blob = bucket.blob(build_investor_path(investor, "master", f"HP_Repayments_Master_{report_date}.csv"))
    df_repay = pd.read_csv(io.StringIO(repay_blob.download_as_text()), low_memory=False)


    summary_df, totals = generate_summary_outputs(
        df_recv, df_repay, report_date, threshold, None
    )

    return render_template(
        "summary.html",
        summary=summary_df.to_dict(orient='records'),
        totals=totals,
        report_date=report_date,
        dpd_threshold=threshold,
        investor=investor
    )



@app.route('/finalise-repurchases', methods=["POST"])
@require_investor
def finalise_repurchase_overrides(investor):
    import pandas as pd
    from google.cloud import storage
    import io
    from datetime import datetime
    from scripts.file_tracker import get_reporting_dates
    from scripts.receivables_allocated import generate_receivables_allocated

    report_date = request.form.get("report_date")
    threshold = int(request.form.get("dpd_threshold", 999))

    # Validate
    if not report_date:
        flash("❌ No report date provided.")
        return redirect(url_for("summary", investor=investor))

    # Dynamically determine prior reporting date
    _, prior_date = get_reporting_dates(reference_date=report_date, investor=investor)
    if not prior_date:
        flash("❌ No prior Repurchases_Master file found.")
        return redirect(url_for("summary", investor=investor))

    gcs = storage.Client()
    bucket = gcs.bucket(GCS_BUCKET)

    # Load Receivables_Allocated for the current period
    recv_blob = bucket.blob(build_investor_path(investor, "outputs", f"Receivables_Allocated_{report_date}.csv"))
    df_recv = pd.read_csv(io.StringIO(recv_blob.download_as_text()), dtype={"LoanID": str})
    df_recv["Due_Date"] = pd.to_datetime(df_recv["Due_Date"], errors="coerce").dt.normalize()
    df_recv["Repurchase_Date"] = pd.to_datetime(df_recv["Repurchase_Date"], errors="coerce").dt.normalize()
    df_recv["Days_Past_Due"] = pd.to_numeric(df_recv["Days_Past_Due"], errors="coerce").fillna(0).astype(int)

    # Select candidates
    to_repurchase = df_recv[
        (df_recv["Days_Past_Due"] >= threshold) & (df_recv["Repurchase_Date"].isna())
    ][["LoanID", "Due_Date"]].copy()

    if not to_repurchase.empty:
        to_repurchase["Repurchase_Date"] = pd.to_datetime(report_date, format="%Y%m%d").normalize()
        to_repurchase["Finalized"] = "TRUE"

    # Load prior Repurchases_Master
    prior_blob = bucket.blob(build_investor_path(investor, "master", f"Repurchases_Master_{prior_date}.csv"))
    try:
        existing = pd.read_csv(io.StringIO(prior_blob.download_as_text()), dtype={"LoanID": str})
        existing["Due_Date"] = pd.to_datetime(existing["Due_Date"], errors="coerce").dt.normalize()
        existing["Repurchase_Date"] = pd.to_datetime(existing["Repurchase_Date"], errors="coerce").dt.normalize()
        print(f"[INFO] Loaded cumulative Repurchases_Master from {prior_date}")
    except Exception as e:
        print(f"[WARN] No prior Repurchases_Master found: {e}")
        existing = pd.DataFrame(columns=["LoanID", "Due_Date", "Repurchase_Date", "Finalized"])

    # Combine and deduplicate
    updated = pd.concat([existing, to_repurchase], ignore_index=True)
    updated.drop_duplicates(subset=["LoanID", "Due_Date"], keep="last", inplace=True)

    # Format dates
    updated["Due_Date"] = pd.to_datetime(updated["Due_Date"], errors="coerce").dt.strftime("%Y-%m-%d")
    updated["Repurchase_Date"] = pd.to_datetime(updated["Repurchase_Date"], errors="coerce").dt.strftime("%Y-%m-%d")

    # Always save back under current report date
    master_blob = bucket.blob(build_investor_path(investor, "master", f"Repurchases_Master_{report_date}.csv"))
    buffer = io.StringIO()
    updated.to_csv(buffer, index=False)
    master_blob.upload_from_string(buffer.getvalue(), content_type="text/csv")

    # Re-generate Receivables_Allocated using this cumulative file
    generate_receivables_allocated(report_date=report_date, bucket=GCS_BUCKET, prior_report_date=prior_date, investor=investor)

    if to_repurchase.empty:
        flash("✅ No new repurchases needed. Prior repurchases were carried forward.")
    else:
        flash(f"✅ Finalised {len(to_repurchase)} new repurchases and updated receivables.")
    return redirect(url_for("payment_summary_route", report_date=report_date, investor=investor))


@app.route("/payment-summary")
@require_investor
def payment_summary_route(investor):
    return payment_summary(GCS_BUCKET, investor)


@app.route("/download-confirmation")
@require_investor
def download_confirmation_route(investor):
    return download_confirmation(GCS_BUCKET, investor)

@app.route("/download-and-return")
@require_investor
def download_and_return(investor):
    report_date = request.args.get("report_date")
    if not report_date:
        flash("❌ No report date provided.")
        return redirect(url_for("summary", investor=investor))

    return render_template("download_and_return.html", report_date=report_date)

@app.route("/download-utilisation")
@require_investor
def download_utilisation_route(investor):
    return generate_utilisation_request(GCS_BUCKET, investor)



@app.route("/download_all_masters")
@require_investor
def download_all_masters(investor):
    import io
    import zipfile
    from flask import send_file, request, redirect, flash
    from google.cloud import storage

    report_date = request.args.get("report_date")
    if not report_date:
        flash("❌ No report date provided.")
        return redirect(url_for("summary", investor=investor))

    client = storage.Client()
    bucket = client.bucket(GCS_BUCKET)

    # 1. List every blob under master/ and filter by date suffix
    blobs = bucket.list_blobs(prefix=f"Investors/{investor}/master/")
    master_blobs = [
        b for b in blobs
        if b.name.lower().endswith(f"_{report_date}.csv")
    ]

    if not master_blobs:
        flash(f"❌ No master files found for {report_date}.")
        return redirect(url_for("summary", investor=investor))

    # 2. Zip them in-memory
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
        for blob in master_blobs:
            data = blob.download_as_bytes()
            filename = blob.name.split("/")[-1]
            zipf.writestr(filename, data)

    zip_buffer.seek(0)

    # 3. Send as a single ZIP download
    return send_file(
        zip_buffer,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"Master_Files_{report_date}.zip"
    )


@app.route("/download_allocations")
@require_investor
def download_allocations(investor):
    import io
    import zipfile
    from flask import send_file, request, redirect, flash
    from google.cloud import storage

    report_date = request.args.get("report_date")
    if not report_date:
        flash("❌ No report date provided.")
        return redirect(url_for("summary", investor=investor))

    client = storage.Client()
    bucket = client.bucket(GCS_BUCKET)

    # find all outputs ending in _{report_date}.csv
    blobs = bucket.list_blobs(prefix=f"Investors/{investor}/outputs/")
    alloc_blobs = [
        b for b in blobs
        if b.name.lower().endswith(f"_{report_date}.csv")
           and ("receivables_allocated" in b.name.lower()
                or "payments_allocated" in b.name.lower())
    ]

    if not alloc_blobs:
        flash(f"❌ No allocation files found for {report_date}.")
        return redirect(url_for("summary", investor=investor))

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for blob in alloc_blobs:
            data = blob.download_as_bytes()
            fname = blob.name.split("/")[-1]
            z.writestr(fname, data)
    buf.seek(0)

    return send_file(
        buf,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"Allocations_{report_date}.zip"
    )




if __name__ == "__main__":
    app.run(debug=True)



######################