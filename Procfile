release: echo "from django.contrib.auth.models import User; User.objects.create_user('snex_user', 'foo@foo.com', 'correcthorsebatterystaple')" | python manage.py shell; pip install https://github.com/TOMToolkit/tom_base/archive/master.zip --upgrade; python manage.py migrate --noinput
web: gunicorn tom20190109.wsgi
