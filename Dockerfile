FROM python:3.8.13-slim-stretch

ENTRYPOINT ["./run.sh"]

RUN apt-get update && apt-get install -y git libpq-dev gcc gfortran mysql-client \
    libmariadbclient-dev libmagic-dev libcfitsio-bin libffi-dev && apt-get autoclean && rm -rf /var/lib/apt/lists/*

COPY . /snex2

RUN pip install numpy && pip install -r /snex2/requirements.txt

WORKDIR /snex2
