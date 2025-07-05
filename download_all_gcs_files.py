import os
from scripts.debiflow_gcs import DebiFlowGCS

BUCKET_NAME = "debiflow-staging"
DOWNLOAD_FOLDER = "downloads"
PREFIXES = [
    "raw/Schedule_", "raw/Payments_", "raw/CustomerDetails_", "raw/HP_Repayments_",
    "master/Schedule_Master_", "master/Payments_Master_", "master/CustomerDetails_Master_", "master/HP_Repayments_Master_"
]

def download_all_files():
    gcs = DebiFlowGCS(BUCKET_NAME)
    blobs = list(gcs.bucket.list_blobs())

    os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

    for prefix in PREFIXES:
        matching = [blob.name for blob in blobs if blob.name.startswith(prefix)]
        for blob_name in matching:
            blob = gcs.bucket.blob(blob_name)
            filename = blob_name.replace("/", "_")
            local_path = os.path.join(DOWNLOAD_FOLDER, filename)
            blob.download_to_filename(local_path)
            print(f"✅ Downloaded: {blob_name} → {local_path}")

if __name__ == "__main__":
    download_all_files()

