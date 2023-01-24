# syntax=docker/dockerfile:1

FROM python:3.10-slim-buster

WORKDIR /cicr-docker

COPY ./impaintingLib    ./impaintingLib
COPY ./impaintingWeb    ./impaintingWeb
COPY ./modelSave        ./modelSave
COPY ./requirements.txt ./requirements.txt
COPY ./QuartApp.py      ./QuartApp.py

RUN pip install -r requirements.txt

EXPOSE 5000

CMD ["hypercorn", "--bind", "localhost:5000", "QuartApp.py"]