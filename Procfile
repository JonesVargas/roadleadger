web: sh -c 'python manage.py migrate --noinput && python manage.py seed_roadledger && exec gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 2 --timeout 120'
