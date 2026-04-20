# Stage 1: Base image with Python
FROM python:3.12-slim AS base

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Set work directory
WORKDIR /app

# Install system dependencies for MySQL and SonarScanner
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    default-libmysqlclient-dev \
    pkg-config \
    wget \
    unzip \
    default-jre-headless \
    && rm -rf /var/lib/apt/lists/* \
    # Download and install SonarScanner
    && wget -q https://binaries.sonarsource.com/Distribution/sonar-scanner-cli/sonar-scanner-cli-5.0.1.3006-linux.zip -O /tmp/sonar-scanner.zip \
    && unzip -q /tmp/sonar-scanner.zip -d /opt/ \
    && mv /opt/sonar-scanner-5.0.1.3006-linux /opt/sonar-scanner \
    && rm /tmp/sonar-scanner.zip \
    && ln -s /opt/sonar-scanner/bin/sonar-scanner /usr/local/bin/sonar-scanner

# Stage 2: Install dependencies
FROM base AS dependencies

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Stage 3: Production image
FROM dependencies AS production

# Copy only runtime files required by the app.
COPY manage.py ./
COPY codemio_back/ ./codemio_back/
COPY authentication/ ./authentication/
COPY analysis/ ./analysis/
COPY projects/ ./projects/

# Run the app with a non-root user.
RUN groupadd --system app && useradd --system --gid app --home /app --shell /usr/sbin/nologin app \
    && chown -R app:app /app

# Expose the port that Render will provide
EXPOSE ${PORT:-8000}

# Create a startup script that collects static files, runs migrations and starts gunicorn
RUN echo '#!/bin/bash\n\
echo "Collecting static files..."\n\
python manage.py collectstatic --noinput\n\
echo "Running database migrations..."\n\
python manage.py migrate --noinput\n\
echo "Starting Gunicorn..."\n\
exec gunicorn codemio_back.wsgi:application \\\n\
  --bind 0.0.0.0:${PORT:-8000} \\\n\
  --workers 4 \\\n\
  --timeout 120 \\\n\
  --access-logfile - \\\n\
  --error-logfile -\n\
' > /app/start.sh && chmod +x /app/start.sh

USER app

# Use the startup script as entrypoint
CMD ["/app/start.sh"]
