FROM python:3.11.9-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install --upgrade pip && python -m pip install -r requirements.txt

COPY . .

RUN SECRET_KEY=build-only-secret-key-not-used-at-runtime DEBUG=False ALLOWED_HOSTS=localhost \
    python manage.py collectstatic --noinput

CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py seed_roadledger && exec gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 2 --timeout 120"]
