release: echo "from django.contrib.auth.models import User; User.objects.create_user('snex_user', 'foo@foo.com', 'correcthorsebatterystaple')" | python manage.py shell; python manage.py migrate --noinput
web: gunicorn tom20190109.wsgi
