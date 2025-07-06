FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Copy app contents
COPY . /app

# Install dependencies
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Set environment variables for Flask
ENV FLASK_APP=main.py
ENV FLASK_RUN_HOST=0.0.0.0
ENV FLASK_RUN_PORT=8080
ENV PYTHONUNBUFFERED=1
# Default bucket; override at runtime if needed
ENV GCS_BUCKET=debiflow-staging

# Expose the port for Cloud Run
EXPOSE 8080

# Start the Flask app
CMD ["gunicorn", "--timeout=900", "--bind=0.0.0.0:8080", "main:app"]
