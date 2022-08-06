FROM python:3.10-slim-buster

EXPOSE 7777
EXPOSE 7788

COPY  requirements.txt /requirements.txt
RUN apt-get update && \
    apt-get install -y gammu && \
    pip3 install --no-cache-dir -r requirements.txt
COPY . /app
