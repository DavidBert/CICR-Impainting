# syntax=docker/dockerfile:1

FROM python:3.10-slim-buster

WORKDIR /cicr-docker

COPY ./impaintingLib    ./impaintingLib
COPY ./impaintingWeb    ./impaintingWeb
COPY ./modelSave        ./modelSave
COPY ./requirements.txt ./requirements.txt
COPY ./QuartApp.py      ./QuartApp.py

# ENV STATIC_URL /static
# ENV STATIC_PATH /var/www/app/static

RUN pip install -r requirements.txt

EXPOSE 5000
EXPOSE 80

ENTRYPOINT ["python"]
CMD ["QuartApp.py"]


# CMD ["hypercorn", "--bind", "localhost:5000", "QuartApp.py"]