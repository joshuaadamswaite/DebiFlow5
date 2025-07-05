# DebiFlow5

DebiFlow5 is a Flask web application for managing investor data stored in Google Cloud Storage. It provides pages for uploading files, generating payment summaries, and other utilities.

## Setup

1. **Python**: Use Python 3.10 or later.
2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
3. **Run the app**:
   ```bash
   flask run
   ```
   The application will start on `http://localhost:5000/` by default.

## Docker

A `Dockerfile` is included. You can build and run the container with:

```bash
# Build the image
docker build -t debiflow5 .

# Run the container
docker run -p 8080:8080 debiflow5
```

The container exposes port 8080 and runs the app with Gunicorn.
