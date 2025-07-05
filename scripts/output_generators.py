import pandas as pd
import numpy as np
import io
import time
from debiflow_gcs import DebiFlowGCS
from scripts.utils import build_investor_path, require_investor

MAX_ALLOCATIONS = 3  # You can adjust this

def generate_payments_allocated(report_date: str, bucket: str, investor):
    t_start = time.time()
    print("[INFO] Starting generate_payments_allocated()")

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
        blob = gcs.bucket.blob(path)
        blob.upload_from_string(df.to_csv(index=False), content_type="text/csv")
        print(f"[TIMER] Wrote {path} in {time.time() - t0:.2f}s")

    try:
        # Load Inputs
        t_load = time.time()
        output_blob = build_investor_path(investor, "outputs", f"Payments_Allocated_{report_date}.csv")

        df_payments = read_csv_from_gcs(investor, "master", f"Payments_Master_{report_date}.csv")
        df_schedule = read_csv_from_gcs(investor, "master", f"Schedule_Master_{report_date}.csv")

        print(f"[TIMER] Total CSV load time: {time.time() - t_load:.2f}s")

        # Standardize column names
        t_norm = time.time()
        df_payments.rename(columns={"originatorLoanID": "LoanID"}, inplace=True)
        df_schedule.rename(columns={"originator_LoanID": "LoanID"}, inplace=True)
        df_payments.sort_values(by=["LoanID", "Paid_Date"], inplace=True)
        df_schedule.sort_values(by=["LoanID", "Due_Date"], inplace=True)
        print(f"[TIMER] Normalisation and sorting time: {time.time() - t_norm:.2f}s")

        # Build schedule dictionaries
        t_dicts = time.time()
        schedule_dict = {
            loan_id: grp['Receivable_Outstandings'].fillna(0).tolist()
            for loan_id, grp in df_schedule.groupby('LoanID')
        }
        cumulative_allocated = {loan_id: [0.0] * len(receivables) for loan_id, receivables in schedule_dict.items()}
        flag_locked = {loan_id: [False] * len(receivables) for loan_id, receivables in schedule_dict.items()}
        print(f"[TIMER] Schedule dict build time: {time.time() - t_dicts:.2f}s")

        # Allocation loop
        t_alloc = time.time()
        allocation_results = []

        for idx, row in df_payments.iterrows():
            loan_id = row['LoanID']
            payment_remaining = row.get('Amount_Paid', 0)
            alloc_row = [0.0] * MAX_ALLOCATIONS
            flag_row = [0] * MAX_ALLOCATIONS
            unallocated_reason = ""

            if pd.isnull(loan_id) or pd.isnull(payment_remaining) or payment_remaining == 0:
                unallocated_reason = "Invalid LoanID or corrupted data"
            elif loan_id not in schedule_dict:
                unallocated_reason = "No receivables found for LoanID"
            else:
                receivables = schedule_dict[loan_id]
                cum_alloc = cumulative_allocated[loan_id]
                flags_done = flag_locked[loan_id]

                if np.nansum(receivables) == 0:
                    unallocated_reason = "Zero or null receivables"
                else:
                    for i in range(min(MAX_ALLOCATIONS, len(receivables))):
                        if payment_remaining <= 0:
                            break
                        receivable_total = receivables[i]
                        allocatable = receivable_total - cum_alloc[i]
                        alloc_amt = min(allocatable, payment_remaining)
                        alloc_amt = round(max(alloc_amt, 0), 2)
                        alloc_row[i] = alloc_amt
                        cum_alloc[i] += alloc_amt
                        payment_remaining -= alloc_amt

                        if not flags_done[i] and np.isclose(cum_alloc[i], receivable_total, atol=0.01):
                            flag_row[i] = 1
                            flags_done[i] = True

                    if sum(alloc_row) == 0:
                        total_receivables = sum(receivables)
                        if np.isclose(sum(cum_alloc), total_receivables, atol=0.01):
                            unallocated_reason = "Receivables already fully allocated"
                        else:
                            unallocated_reason = "Duplicate payment for already settled receivable"

            result = row.to_dict()
            for i in range(MAX_ALLOCATIONS):
                result[f'Payment_Allocation_pmt{i+1}'] = alloc_row[i]
                result[f'Payment_Allocation_flag{i+1}'] = flag_row[i]
            result['Unallocated_Reason'] = unallocated_reason

            allocation_results.append(result)

            if (idx + 1) % 1000 == 0 or idx == len(df_payments) - 1:
                print(f"[INFO] Processed {idx+1:,} of {len(df_payments):,} payments")

        print(f"[TIMER] Allocation loop time: {time.time() - t_alloc:.2f}s")

        # DataFrame assembly and rounding
        t_df = time.time()
        df_final = pd.DataFrame(allocation_results)
        payment_cols = [col for col in df_final if col.startswith('Payment_Allocation_pmt')]
        df_final[payment_cols] = df_final[payment_cols].round(2)
        print(f"[TIMER] DataFrame assembly time: {time.time() - t_df:.2f}s")

        # Write output
        write_csv_to_gcs(df_final, output_blob)

        print(f"[SUCCESS] Payments_Allocated file saved: {output_blob}")
        print(f"[TIMER] Total runtime: {time.time() - t_start:.2f}s")

    except Exception as e:
        print(f"[ERROR] Failed to generate Payments_Allocated: {e}")
