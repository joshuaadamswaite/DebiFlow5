import sys
import os
from google.cloud import storage

BUCKET_NAME = os.getenv("GCS_BUCKET", "debiflow-staging")

def list_uploaded_files(investor):
    prefix = f"raw/{investor}/"
    client = storage.Client()
    bucket = client.bucket(BUCKET_NAME)
    blobs = bucket.list_blobs(prefix=prefix)

    print(f"📂 Files under gs://{BUCKET_NAME}/{prefix}")
    for blob in blobs:
        print(" -", blob.name)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python list_uploaded_files.py <investor>")
        sys.exit(1)

    investor_arg = sys.argv[1].strip()
    list_uploaded_files(investor_arg)
