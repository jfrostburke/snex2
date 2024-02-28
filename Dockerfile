FROM python:3.9-slim

ENTRYPOINT ["./run.sh"]

RUN apt-get update && apt-get install -y git libpq-dev gcc gfortran mariadb-client \
    libmariadb-dev libmagic-dev libcfitsio-bin libffi-dev libgsl-dev && apt-get autoclean && rm -rf /var/lib/apt/lists/*

COPY . /snex2

RUN pip3 install --upgrade pip

RUN pip install numpy && pip install -r /snex2/requirements.txt

RUN pip uninstall -y ligo.skymap 
RUN pip install ligo.skymap

WORKDIR /snex2
