from google.cloud import storage
import re
from collections import defaultdict
from scripts.utils import build_investor_path
import os

REQUIRED_PREFIXES = ["Payments_", "Schedule_", "CustomerDetails_", "HP_Repayments_"]
RAW_FOLDER       = "raw/"
MASTER_FOLDER    = "master/"
DEFAULT_BUCKET   = "debiflow-staging"

def get_reporting_dates(bucket_name: str = DEFAULT_BUCKET,
                        reference_date: str = None,
                        investor: str = None):
    """
    Always returns a tuple: (latest_raw, previous_master)
    
    - latest_raw: the most recent raw‐batch date (all prefixes present)
      ≤ reference_date (if given), or overall latest otherwise.
    - previous_master: the most recent master date < cutoff, where cutoff is
      reference_date if provided, or latest_raw otherwise.
    """

    client = storage.Client()
    bucket = client.bucket(bucket_name)

    # === Collect master dates ===
    master_prefix = build_investor_path(investor, "master", "")
    master_dates = {
        m.group(1)
        for blob in bucket.list_blobs(prefix=master_prefix)
        for m in [re.search(r"_Master_(\d{8})\.csv$", blob.name)]
        if m
    }


    # === Collect raw dates with complete prefixes ===
    raw_map = defaultdict(set)
    raw_prefix = build_investor_path(investor, "raw", "")
    for blob in bucket.list_blobs(prefix=raw_prefix):
        fname = os.path.basename(blob.name)
        for prefix in REQUIRED_PREFIXES:
            m = re.match(rf"{prefix}(\d{{8}})\.csv$", fname)
            if m:
                raw_map[m.group(1)].add(prefix)

    complete_raw = sorted(
        dt for dt, prefixes in raw_map.items()
        if len(prefixes) == len(REQUIRED_PREFIXES)
    )

    # === If reference_date is given, filter both lists to ≤ reference_date ===
    if reference_date:
        complete_raw   = [d for d in complete_raw if d <= reference_date]
        master_dates   = {d for d in master_dates   if d <= reference_date}

    # === Determine latest_raw ===
    latest_raw = complete_raw[-1] if complete_raw else None

    # === Determine previous_master (< cutoff) ===
    cutoff = reference_date or latest_raw
    prior_masters = sorted(d for d in master_dates if d < cutoff)
    previous_master = prior_masters[-1] if prior_masters else None

    print("==== DEBUG FINAL ====")
    print("reference_date =", reference_date)
    print("master_dates =", master_dates)
    print("complete_raw =", complete_raw)
    print("latest_raw =", latest_raw)
    print("prior_masters =", prior_masters)
    print("previous_master =", previous_master)
    return latest_raw, previous_master
