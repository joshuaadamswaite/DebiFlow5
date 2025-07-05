import sys
from google.cloud import storage

def list_master_blobs(investor, bucket_name="debiflow-staging"):
    prefix = f"master/{investor}/"
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blobs = bucket.list_blobs(prefix=prefix)

    print(f"📦 Master folder contents under gs://{bucket_name}/{prefix}")
    for blob in blobs:
        print("-", blob.name)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python list_master_blobs.py <investor>")
        sys.exit(1)

    investor_arg = sys.argv[1].strip()
    list_master_blobs(investor_arg)
