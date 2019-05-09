FROM python:3.7.3-slim-stretch

ENTRYPOINT ["./run.sh"]

RUN apt-get update && apt-get install -y git libpq-dev gcc && apt-get autoclean && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir numpy && pip install --no-cache-dir dataclasses django git+https://github.com/TOMToolkit/tom_base.git#egg=tomtoolkit gunicorn django-heroku django-storages boto3

COPY . /snex2

WORKDIR /snex2
