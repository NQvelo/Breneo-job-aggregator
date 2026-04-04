web: sh -c 'python manage.py migrate --noinput && exec gunicorn job_aggregator.wsgi --bind 0.0.0.0:${PORT:-8080} --log-file - --timeout 300 --workers 1 --preload'
