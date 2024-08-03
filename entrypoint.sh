#!/usr/bin/env bash

chmod +x /app/blackvueconcat.sh

/app/blackvueconcat.sh \
    && [[ -z $RUN_ONCE ]] \
    && cron -f
