FROM python:3.10-slim-buster

EXPOSE 7777
EXPOSE 7788

COPY requirements.txt /requirements.txt
RUN apt update && \
    apt install -y gcc socat vim libgammu-dev && \
    pip3 install --no-cache-dir -r requirements.txt && \
    apt purge -y gcc && \
    apt autoremove -y
COPY . /app
