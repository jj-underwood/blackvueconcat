FROM debian:buster-slim AS base

RUN apt update && \
    apt upgrade -y

FROM base AS packages

ENV DEBIAN_FRONTEND noninteractive

RUN apt update && \
    apt install -y \
    ffmpeg \
    cron && \
    apt autoremove -y && \
    apt clean -y

FROM packages AS python

RUN apt install -y \
    python3-dev \
    python3-pip && \
    python3 -m pip install --upgrade pip && \
    python3 -m pip install filelock

FROM python AS script

RUN mkdir /app
WORKDIR /app

ADD crontab /etc/cron.d/blackvueconcat
RUN crontab /etc/cron.d/blackvueconcat
RUN touch /var/log/cron.log

ENV LOGGING_LEVEL="" \
    SOURCE_DIR="" \
    WORK_DIR="" \
    OUTPUT_DIR="" \
    CONSECUTIVE_THRESHOLD="" \
    CONCAT_THRESHOLD="" \
    RETENTION=""\
    INITIAL_IMPACT="" \
    NO_OUTPUT="" \
    OVERWRITE="" \
    RUN_ONCE=""

ENTRYPOINT ["/bin/bash", "./entrypoint.sh"]
