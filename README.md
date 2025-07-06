# DebiFlow5

DebiFlow5 is a Flask-based web application for managing investor loan and repayment data stored in Google Cloud Storage (GCS).  
It provides workflows for uploading raw data, generating payment allocations, summarizing receivables, and downloading processed outputs.

---

## Project Structure

app/
├── main.py # Flask application entry point
├── scripts/ # Core business logic modules
├── templates/ # HTML templates
├── requirements.txt # Python dependencies
├── Dockerfile # Production deployment container
debiflow-gcs-key.json # (Your GCS credentials, not committed)


---

## Setup

### 1. Prerequisites
- Python 3.10 or later
- A Google Cloud project with GCS buckets configured
- A service account JSON key for GCS access

---

### 2. Install dependencies

Create and activate a virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate
Install packages:

pip install -r requirements.txt
3. Configure credentials
Set the environment variable so the app can authenticate:

export GOOGLE_APPLICATION_CREDENTIALS="/absolute/path/to/debiflow-gcs-key.json"
In Codespaces, use:

export GOOGLE_APPLICATION_CREDENTIALS="/workspaces/DebiFlow5/debiflow-gcs-key.json"
4. Run the app locally
Run via Python:

python main.py
The app will start on http://127.0.0.1:5000.

Codespaces Usage

If you use GitHub Codespaces:

Upload debiflow-gcs-key.json into the workspace root.
Set the environment variable:
export GOOGLE_APPLICATION_CREDENTIALS="/workspaces/DebiFlow5/debiflow-gcs-key.json"
Start the app:
python main.py
Forward port 5000 via the Ports panel and open it in your browser.
Docker Deployment

A Dockerfile is included for production deployment using Gunicorn.

Build the image:

docker build -t debiflow5 .
Run the container:

docker run \
  -e GOOGLE_APPLICATION_CREDENTIALS=/app/debiflow-gcs-key.json \
  -v /path/to/your/credentials.json:/app/debiflow-gcs-key.json \
  -p 8080:8080 \
  debiflow5
The app will be available at http://localhost:8080.

Note: Replace /path/to/your/credentials.json with the actual path to your GCS key.

Security Notes

Never commit debiflow-gcs-key.json or .env files.
Always use environment variables or Docker secrets to manage credentials.
For production, use Gunicorn and debug=False.
Future Enhancements

GitHub Actions CI/CD workflows
Automated testing
Role-based access control
License

This project is proprietary. All rights reserved.