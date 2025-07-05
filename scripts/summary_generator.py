import pandas as pd
import numpy as np

def generate_summary_outputs(
    receivables_df: pd.DataFrame,
    hp_repayments_df: pd.DataFrame,
    report_date: str,
    threshold: int = 999,
    repurchase_override_df: pd.DataFrame = None
):
    # === Clean & prep data ===
    receivables_df['Due_Date'] = pd.to_datetime(receivables_df['Due_Date'], errors='coerce')
    receivables_df['Allocation_Date'] = pd.to_datetime(receivables_df['Allocation_Date'], errors='coerce')
    receivables_df['Repurchase_Date'] = pd.to_datetime(receivables_df['Repurchase_Date'], errors='coerce')
    receivables_df['Days_Past_Due'] = pd.to_numeric(receivables_df['Days_Past_Due'], errors='coerce').fillna(0).astype(int)

    hp_repayments_df['HP_Repayment_Date'] = pd.to_datetime(
        hp_repayments_df['HP_Repayment_Date'], format="%Y-%m-%d", errors="coerce"
    )

    hp_repayments_df["HP_Repayment_Amount"] = pd.to_numeric(
    hp_repayments_df["HP_Repayment_Amount"], errors="coerce").fillna(0)

    total_paid = hp_repayments_df['HP_Repayment_Amount'].sum()

    # === Apply repurchase overrides if present ===
    if repurchase_override_df is not None and not repurchase_override_df.empty:
        repurchase_override_df = repurchase_override_df.copy()
        repurchase_override_df['Repurchase_Date'] = pd.to_datetime(repurchase_override_df['Repurchase_Date'], errors='coerce')
        repurchase_override_df['Due_Date'] = pd.to_datetime(repurchase_override_df['Due_Date'], errors='coerce', format="%Y/%m/%d")

        receivables_df = pd.merge(
            receivables_df.drop(columns=['Repurchase_Date'], errors='ignore'),
            repurchase_override_df[['LoanID', 'Due_Date', 'Repurchase_Date']],
            on=['LoanID', 'Due_Date'],
            how='left'
        )

    # === Simulate threshold-based repurchases (for display only)
    simulated = receivables_df.copy()
    simulated['Sim_Repurchase'] = False
    simulated.loc[
        (simulated['Days_Past_Due'] >= threshold) &
        (simulated['Repurchase_Date'].isna()),
        'Sim_Repurchase'
    ] = True


    receivables_df["Minimum_Recovery_Amount"] = pd.to_numeric(
    receivables_df["Minimum_Recovery_Amount"], errors="coerce").fillna(0)

    # ✅ TRUE total due (unfiltered sum of all Minimum_Recovery_Amount)
    total_due = receivables_df['Minimum_Recovery_Amount'].sum()

    # ✅ PAR accounts = remaining unrepaid + unallocated + unrepurchased
    unrepaid = simulated[
        (simulated['Allocation_Date'].isna()) &
        (simulated['Repurchase_Date'].isna()) &
        (~simulated['Sim_Repurchase'])
    ].copy()

    # Compute max DPD per LoanID
    max_dpd_per_loan = unrepaid.groupby('LoanID')['Days_Past_Due'].transform('max')



    # Annotate each row
    unrepaid['Max_Days_Past_Due_Per_Loan'] = max_dpd_per_loan

    # ✅ Clean Purchase_Consideration in unrepaid (important)
    unrepaid["Purchase_Consideration"] = pd.to_numeric(
    unrepaid["Purchase_Consideration"], errors="coerce"
    ).fillna(0)

    receivables_df["Purchase_Consideration"] = pd.to_numeric(
    receivables_df["Purchase_Consideration"], errors="coerce").fillna(0)



    total_portfolio = unrepaid['Purchase_Consideration'].sum()

    # === Compute bucket values
    bucket_definitions = {
        "Current": lambda df: df['Max_Days_Past_Due_Per_Loan'] == 0,
        "PAR1": lambda df: df['Max_Days_Past_Due_Per_Loan'] >= 1,
        "PAR7": lambda df: df['Max_Days_Past_Due_Per_Loan'] >= 7,
        "PAR30": lambda df: df['Max_Days_Past_Due_Per_Loan'] >= 30,
        "PAR60": lambda df: df['Max_Days_Past_Due_Per_Loan'] >= 60,
        "PAR90": lambda df: df['Max_Days_Past_Due_Per_Loan'] >= 90,
        "PAR120": lambda df: df['Max_Days_Past_Due_Per_Loan'] >= 120,
        "PAR150": lambda df: df['Max_Days_Past_Due_Per_Loan'] >= 150,
        "PAR180+": lambda df: df['Max_Days_Past_Due_Per_Loan'] >= 180,
    }

    summary_data = []
    for bucket, condition in bucket_definitions.items():
        value = unrepaid.loc[condition(unrepaid), 'Purchase_Consideration'].sum()
        percentage = (value / total_portfolio * 100) if total_portfolio > 0 else 0
        summary_data.append({
            "Bucket": bucket,
            "Value": f"{value:,.2f}".replace(",", " "),
            "Percentage of Total": f"{percentage:.2f}%"
        })

    summary_data.append({
        "Bucket": "Total",
        "Value": f"{total_portfolio:,.2f}".replace(",", " "),
        "Percentage of Total": "100.00%"
    })

    summary_df = pd.DataFrame(summary_data)

    totals = {
        'total_due': f"{total_due:,.2f}".replace(",", " "),
        'total_paid': f"{total_paid:,.2f}".replace(",", " "),
        'total_portfolio': f"{total_portfolio:,.2f}".replace(",", " "),
        'total_due_on_date': f"{(total_due - total_paid):,.2f}".replace(",", " ")
    }

    return summary_df, totals
