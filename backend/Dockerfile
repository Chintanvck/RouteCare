FROM python:3.12-slim

WORKDIR /app

# System deps needed for psycopg2 and OR-Tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Dev-only image: runs as root and bind-mounts ./backend over /app (see docker-compose.yml), so a
# non-root USER isn't set here - a container-baked UID can't reliably write a host bind-mount owned
# by whatever user owns the checkout on the host. See Dockerfile.prod for the hardened, non-root
# production image built from this same source instead.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request as u; u.urlopen('http://localhost:8000/health/live', timeout=3)" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]