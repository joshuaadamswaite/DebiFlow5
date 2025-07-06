# DebiFlow

DebiFlow is a Flask-based application for managing loan repayment data using Google Cloud Storage.

## Configuration

Set the GCS bucket name via the `GCS_BUCKET` environment variable. If unset, the app defaults to `debiflow-staging`.

```
export GCS_BUCKET=my-debiflow-bucket
```

## Running in Codespaces

Install dependencies and start the server:

```
pip install -r requirements.txt
flask run --host=0.0.0.0 --port=8080
```

## Docker

The Dockerfile sets `GCS_BUCKET` to `debiflow-staging` by default. Build and run the container, overriding the variable if needed:

```
docker build -t debiflow .
docker run -p 8080:8080 -e GCS_BUCKET=my-debiflow-bucket debiflow
```
