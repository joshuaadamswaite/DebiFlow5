import pandas as pd
import numpy as np
import io
import time
from datetime import datetime, timedelta
from scripts.debiflow_gcs import DebiFlowGCS
from scripts.utils import build_investor_path, require_investor

def generate_receivables_allocated(report_date: str, bucket: str, prior_report_date: str, investor):
    t_start = time.time()
    print("[INFO] Starting generate_receivables_allocated()")

    report_date_dt = datetime.strptime(report_date, "%Y%m%d")

    gcs = DebiFlowGCS(bucket)

    def read_csv_from_gcs(investor, folder, filename):
        t0 = time.time()
        path = build_investor_path(investor, folder, filename)
        blob = gcs.bucket.blob(path)
        df = pd.read_csv(io.StringIO(blob.download_as_text()), dtype={"LoanID": str}, low_memory=False)
        print(f"[TIMER] Loaded {path} in {time.time() - t0:.2f}s")
        return df

    def write_csv_to_gcs(df, path):
        t0 = time.time()
        try:
            blob = gcs.bucket.blob(path)
            blob.upload_from_string(df.to_csv(index=False), content_type="text/csv")
            print(f"[UPLOAD] Wrote {path} in {time.time() - t0:.2f}s")
        except Exception as e:
            print(f"[ERROR] Upload failed for {path}: {e}")

    try:
        # Load Inputs
        t_load = time.time()
        output_blob = build_investor_path(investor, "outputs", f"Receivables_Allocated_{report_date}.csv")

        df_schedule = read_csv_from_gcs(investor, "master", f"Schedule_Master_{report_date}.csv")
        df_payments = read_csv_from_gcs(investor, "outputs", f"Payments_Allocated_{report_date}.csv")

        print(f"[TIMER] Total CSV load time: {time.time() - t_load:.2f}s")

        # Clean Schedule
        t_clean = time.time()
        df_schedule.columns = [col.strip() for col in df_schedule.columns]
        df_schedule.rename(columns={"originator_LoanID": "LoanID"}, inplace=True)
        df_schedule['LoanID'] = df_schedule['LoanID'].astype(str).str.strip()
        df_schedule = df_schedule.dropna(how="all")
        df_schedule = df_schedule[df_schedule['LoanID'].notna()]
        df_schedule['Due_Date'] = pd.to_datetime(df_schedule['Due_Date'], errors="coerce").dt.normalize()
        df_schedule['Purchase_Date'] = pd.to_datetime(df_schedule['Purchase_Date'], errors="coerce").dt.normalize()
        print(f"[TIMER] Schedule cleaning: {time.time() - t_clean:.2f}s")

        # Pre-allocate
        df_calc = df_schedule.copy().reset_index(drop=True)
        df_calc["Receivable_Index"] = df_calc.groupby("LoanID").cumcount() + 1
        df_calc["RowID"] = df_calc.index

        # Clean Payments
        t_payments = time.time()
        df_payments.columns = [col.strip() for col in df_payments.columns]
        df_payments['LoanID'] = df_payments['LoanID'].astype(str).str.strip()
        df_payments['Paid_Date'] = pd.to_datetime(df_payments['Paid_Date'], errors="coerce").dt.normalize()
        print(f"[TIMER] Payments cleaning: {time.time() - t_payments:.2f}s")

        # Transform to long format
        t_long = time.time()
        payment_cols = [col for col in df_payments.columns if col.startswith("Payment_Allocation_pmt")]
        payment_long = pd.DataFrame()
        for i, pmt_col in enumerate(payment_cols):
            flag_col = f"Payment_Allocation_flag{i+1}"
            temp = df_payments[["LoanID", "Paid_Date", pmt_col, flag_col]].copy()
            temp.rename(columns={pmt_col: "Payment_allocated", flag_col: "Flag"}, inplace=True)
            temp["Receivable_Index"] = i + 1
            payment_long = pd.concat([payment_long, temp], axis=0)
        print(f"[TIMER] Payment long transformation: {time.time() - t_long:.2f}s")

        # Filter allocated payments
        t_filter = time.time()
        payment_long = payment_long[payment_long["Flag"] == 1]
        payment_long = payment_long.drop_duplicates(subset=["LoanID", "Receivable_Index"])
        payment_long.rename(columns={"Paid_Date": "Allocation_Date"}, inplace=True)
        payment_long = payment_long[["LoanID", "Receivable_Index", "Payment_allocated", "Allocation_Date"]]
        print(f"[TIMER] Payment filtering: {time.time() - t_filter:.2f}s")

        # Merge allocations
        t_merge1 = time.time()
        df_calc = df_calc.merge(payment_long, on=["LoanID", "Receivable_Index"], how="left")
        df_calc["Payment_allocated"] = df_calc["Payment_allocated"].fillna(0).round(2)
        print(f"[TIMER] Merge allocations: {time.time() - t_merge1:.2f}s")

        # Merge finalized repurchases from previous reporting period
        t_prev = time.time()
        if not prior_report_date:
            raise ValueError("prior_report_date must be provided to ensure correct repurchase continuity.")
        prior_date_str = prior_report_date

        try:
            df_prev = read_csv_from_gcs(investor, "master", f"Repurchases_Master_{prior_date_str}.csv")
            df_prev.columns = [col.strip() for col in df_prev.columns]
            df_prev['LoanID'] = df_prev['LoanID'].astype(str).str.strip()
            df_prev['Due_Date'] = pd.to_datetime(df_prev['Due_Date'], errors="coerce").dt.normalize()
            df_prev['Repurchase_Date'] = pd.to_datetime(df_prev['Repurchase_Date'], errors="coerce").dt.normalize()
            df_prev = df_prev[df_prev['Finalized'].astype(str).str.upper().str.strip() == "TRUE"]
            df_prev = df_prev.drop_duplicates(subset=["LoanID", "Due_Date"])

            df_calc = df_calc.merge(
                df_prev[['LoanID', 'Due_Date', 'Repurchase_Date']],
                on=['LoanID', 'Due_Date'],
                how='left'
            )
            print(f"[TIMER] Merge previous repurchases: {time.time() - t_prev:.2f}s")
        except Exception as e:
            print(f"[WARN] No finalized Repurchase_Master found for previous master week: {e}")
            df_calc["Repurchase_Date"] = pd.NaT

        # Merge current repurchase overrides
        t_curr = time.time()
        try:
            df_overrides = read_csv_from_gcs(investor, "master", f"Repurchases_Master_{report_date}.csv")
            df_overrides.columns = [col.strip() for col in df_overrides.columns]
            df_overrides['LoanID'] = df_overrides['LoanID'].astype(str).str.strip()
            df_overrides['Due_Date'] = pd.to_datetime(df_overrides['Due_Date'], errors="coerce").dt.normalize()
            df_overrides['Repurchase_Date'] = pd.to_datetime(df_overrides['Repurchase_Date'], errors="coerce").dt.normalize()
            df_overrides = df_overrides[df_overrides['Finalized'].astype(str).str.upper().str.strip() == "TRUE"]
            df_overrides = df_overrides.drop_duplicates(subset=["LoanID", "Due_Date"])

            df_calc = df_calc.merge(
                df_overrides[["LoanID", "Due_Date", "Repurchase_Date"]],
                on=["LoanID", "Due_Date"],
                how="left",
                suffixes=("", "_override")
            )
            df_calc["Repurchase_Date"] = df_calc["Repurchase_Date"].combine_first(df_calc["Repurchase_Date_override"])
            df_calc.drop(columns=["Repurchase_Date_override"], inplace=True)
            print(f"[TIMER] Merge current repurchases: {time.time() - t_curr:.2f}s")
        except Exception as e:
            print(f"[WARN] No current Repurchase_Master: {e}")

        # Calculate Days Past Due
        t_dpd = time.time()
        due_mask = (
            (df_calc['Payment_allocated'] == 0) &
            (df_calc['Repurchase_Date'].isna()) &
            (df_calc['Due_Date'] < report_date_dt)
        )
        df_calc['Days_Past_Due'] = np.where(
            due_mask,
            (report_date_dt - df_calc['Due_Date']).dt.days,
            0
        )
        print(f"[TIMER] Days Past Due calculation: {time.time() - t_dpd:.2f}s")

        # Calculate Minimum Recovery Amount (If no repurchase date is provided, Allocation date is used.ie. Allocation_Date will only be used if Repurchase_Date is missing)
        t_mra = time.time()
        cutoff = df_calc['Repurchase_Date'].combine_first(df_calc['Allocation_Date'])
        cutoff = pd.to_datetime(cutoff, errors="coerce")
        cutoff[~((cutoff > "1900-01-01") & (cutoff < "2100-01-01"))] = pd.NaT
        days_elapsed = (cutoff - df_calc['Purchase_Date']).dt.days.fillna(0)
        has_cutoff = df_calc['Allocation_Date'].notna() | df_calc['Repurchase_Date'].notna()
        df_calc['Minimum_Recovery_Amount'] = np.where(
            has_cutoff,
            (df_calc['Purchase_Consideration'] * (1 + df_calc['Advance_Rate'] * days_elapsed / 365)).round(2),
            np.nan
        )
        print(f"[TIMER] Minimum Recovery Amount calculation: {time.time() - t_mra:.2f}s")

        # Final cleanup
        df_calc.sort_values("RowID", inplace=True)
        df_calc.drop(columns=["RowID"], inplace=True)

        write_csv_to_gcs(df_calc, output_blob)
        print(f"[TIMER] Total runtime: {time.time() - t_start:.2f}s")

    except Exception as e:
        print(f"[ERROR] Failed to generate Receivables_Allocated: {e}")
