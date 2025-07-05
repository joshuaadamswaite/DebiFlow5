from google.cloud import storage
from scripts.utils import build_investor_path, require_investor

class DebiFlowGCS:
    def __init__(self, bucket_name: str):
        self.client = storage.Client()
        self.bucket = self.client.bucket(bucket_name)

    def upload_file(self, local_path: str, gcs_path: str):
        blob = self.bucket.blob(gcs_path)
        blob.upload_from_filename(local_path)
        print(f"✅ Uploaded: {local_path} → gs://{self.bucket.name}/{gcs_path}")

    def download_file(self, gcs_path: str, local_path: str):
        blob = self.bucket.blob(gcs_path)
        blob.download_to_filename(local_path)
        print(f"⬇️  Downloaded: gs://{self.bucket.name}/{gcs_path} → {local_path}")

    def list_files(self, investor: str, subfolder: str, extra_prefix: str = ""):
        """
        List files scoped to an investor and subfolder.
        """
        prefix = build_investor_path(investor, subfolder, extra_prefix)
        blobs = self.client.list_blobs(self.bucket, prefix=prefix)
        file_list = [blob.name for blob in blobs]
        print(f"📦 Files in {prefix}:")
        for name in file_list:
            print("-", name)
        return file_list

    def delete_file(self, gcs_path: str):
        blob = self.bucket.blob(gcs_path)
        blob.delete()
        print(f"🗑️ Deleted: gs://{self.bucket.name}/{gcs_path}")

