#!/usr/bin/env bash

logging_level=${LOGGING_LEVEL:+--logging-level $LOGGING_LEVEL}
sourcedir=${SOURCE_DIR:+--source-dir $SOURCE_DIR}
workdir=${WORK_DIR:+--work-dir $WORK_DIR}
outputdir=${OUTPUT_DIR:+--output-dir $OUTPUT_DIR}
consecutive_threshold=${CONSECUTIVE_THRESHOLD:+--consecutive-threshold $CONSECUTIVE_THRESHOLD}
concat_threshold=${CONCAT_THRESHOLD:+--concat-threshold $CONCAT_THRESHOLD}
retention=${RETENTION:+--retention $RETENTION}
initial_impact="${INITIAL_IMPACT:+--initial-impact}"
no_output="${NO_OUTPUT:+--no-output}"
overwrite="${OVERWRITE:+--overwrite}"

python3 /app/blackvueconcat.py ${logging_level} ${sourcedir} ${workdir} ${outputdir} ${consecutive_thoreshold} ${concat_threshold} ${retention} ${initial_impact} ${no_output} ${overwrite}
