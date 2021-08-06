FROM python:3.7-alpine

EXPOSE 7777
EXPOSE 7788

RUN pip install --upgrade pip

RUN mkdir /app
WORKDIR /app

COPY requirements.txt /app/requirements.txt

RUN apk add --update --no-cache socat openssh-client gammu-dev gammu libxml2-dev libxslt-dev \
	&& apk add --no-cache --virtual .build-deps \
		mariadb-dev \
		gcc \
		g++ \
		musl-dev \
                openssl-dev \
                libffi-dev \
        && pip install -r requirements.txt \
	&& apk del .build-deps

COPY . /app
