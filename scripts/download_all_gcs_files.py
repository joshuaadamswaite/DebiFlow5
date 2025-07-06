import os
import sys
from scripts.debiflow_gcs import DebiFlowGCS

BUCKET_NAME = os.getenv("GCS_BUCKET", "debiflow-staging")
DOWNLOAD_FOLDER = "downloads"
FILE_TYPES = ["Schedule", "Payments", "CustomerDetails", "HP_Repayments"]

def download_latest_files(investor):
    gcs = DebiFlowGCS(BUCKET_NAME)
    blobs = list(gcs.bucket.list_blobs())

    os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

    for file_type in FILE_TYPES:
        for location in ["raw", "master"]:
            prefix = f"{location}/{investor}/{file_type}"

            matches = [
                blob.name for blob in blobs
                if blob.name.startswith(prefix)
            ]

            if not matches:
                print(f"⚠️ No file found for: {prefix}")
                continue

            latest_blob = sorted(matches)[-1]
            filename = latest_blob.replace("/", "_")
            local_path = os.path.join(DOWNLOAD_FOLDER, filename)

            blob = gcs.bucket.blob(latest_blob)
            blob.download_to_filename(local_path)
            print(f"✅ Downloaded: {latest_blob} → {local_path}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python download_latest_files.py <investor>")
        sys.exit(1)

    investor_arg = sys.argv[1].strip()
    download_latest_files(investor_arg)
