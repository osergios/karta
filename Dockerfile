FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/srv/vendor

WORKDIR /srv
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY vendor ./vendor
COPY app ./app

# The database lives in /data (DB_PATH). Create it owned by the app user, so a new Docker volume
# mounted there inherits that owner and the app can write to it.
RUN mkdir -p /data && chown 10001:10001 /data
VOLUME /data

USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-server-header", "--no-access-log"]
