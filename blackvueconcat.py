#!/usr/bin/env python3

import argparse
import datetime
from filelock import FileLock
import json
import logging
import os
import re
import subprocess
import sys
import time

logging.basicConfig(
    format='[%(asctime)s] {%(pathname)s:%(lineno)d} %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/app/blackvueconcat.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger('')

PATTERN_RECORDINGS = r'(\d+_\d+)_([A-Z]+)\.(.+)'
PATTERN_WORKFILES = r'(\d+_\d+)-(\d+_\d+)_([A-Z]+)\.(.+)'
PATTERN_OUTPUTFILES = r'(\d+_\d+)-(\d+_\d+)_([A-Z]+)\.(.+)'

VALID_LOGGING_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")

DEFAULT_VALUES = {
    'logging_level': VALID_LOGGING_LEVELS[2],
    'sourcedir': os.getcwd(),
    'workdir': os.getcwd(),
    'outputdir': os.getcwd(),
    'consecutive_threshold': 64,
    'concat_threshold': 2,
    'retention': 14
}

def get_options():

    parser = argparse.ArgumentParser()
    parser.add_argument('--logging-level', choices=VALID_LOGGING_LEVELS, default=DEFAULT_VALUES['logging_level'])
    parser.add_argument('--source-dir', default=DEFAULT_VALUES['sourcedir'], help='Directory where recording files are stored.')
    parser.add_argument('--work-dir', default=DEFAULT_VALUES['workdir'], help='Directory for work files.')
    parser.add_argument('--output-dir', default=DEFAULT_VALUES['outputdir'], help='Directory for output files (concatenated recordings).')
    parser.add_argument('--consecutive-threshold', default=DEFAULT_VALUES['consecutive_threshold'], type=int, help='If timestamp difference is less than the threshold, they are consecutive.')
    parser.add_argument('--concat-threshold', default=DEFAULT_VALUES['concat_threshold'], type=int, help='If the number of consecutive videos is less than the threshold, they are concatenated.')
    parser.add_argument('--retention', default=DEFAULT_VALUES['retention'], type=int, help='Retention days of concatenated recordings.')
    parser.add_argument('--initial-impact', action='store_true', help='If set, a first impact event of a concatenated recordings is kept included.')
    parser.add_argument('--no-output', action='store_true', help='If set, output files are not created.')
    parser.add_argument('--overwrite', action='store_true', help='If set, overwrite work and output files.')

    args = parser.parse_args()

    return args

def set_logging_level(options):
    if options.logging_level == 'DEBUG':
        logger.setLevel(logging.DEBUG)
    elif options.logging_level == 'INFO':
        logger.setLevel(logging.INFO)
    elif options.logging_level == 'WARNING':
        logger.setLevel(logging.WARNING)
    elif options.logging_level == 'ERROR':
        logger.setLevel(logging.ERROR)
    elif options.logging_level == 'CRITICAL':
        logger.setLevel(logging.CRITICAL)

def create_chunks(options):
    chunks = []
    files = sorted(os.listdir(options.source_dir))
    pattern = re.compile(PATTERN_RECORDINGS)
    for f in files:
        if not os.path.isfile(os.path.join(options.source_dir, f)):
            continue
        matches = pattern.match(f)
        if not matches:
            continue
        datetime_obj = datetime.datetime.strptime(matches.group(1), '%Y%m%d_%H%M%S')


        obj = {'datetime': datetime_obj,
               'type': matches.group(2),
               'ext': matches.group(3),
               'dir': options.source_dir,
               'filename': f}

        if len(chunks) == 0:
            chunks.append([])
            chunks[-1].append(obj)
            continue

        if obj['datetime'] == chunks[-1][-1]['datetime']:
            chunks[-1].append(obj)
            continue

        duration = obj['datetime'] - chunks[-1][-1]['datetime']
        if int(duration.total_seconds()) <= options.consecutive_threshold:
            if options.initial_impact:
                chunks[-1].append(obj)
            else:
                impact_flag = 0
                for item in chunks[-1]:
                    if item['type'].startswith('I'):
                        impact_flag += 1
                if len(chunks[-1]) == impact_flag:
                    if obj['type'].startswith('I'):
                        chunks[-1].append(obj)
                    else:
                        chunks.append([])
                        chunks[-1].append(obj)
                else:
                    chunks[-1].append(obj)
        else:
            chunks.append([])
            chunks[-1].append(obj)
    return chunks

def process_chunks(options, chunks):
    for chunk in chunks:
        videos_f = []
        videos_r = []
        time_start = chunk[0]['datetime'].strftime('%Y%m%d_%H%M%S')
        time_end = chunk[-1]['datetime'].strftime('%Y%m%d_%H%M%S')
        logger.debug('{}-{}'.format(time_start, time_end))
        if chunk[0]['datetime'].date() == chunk[-1]['datetime'].date():
            title = '{} - {}'.format(chunk[0]['datetime'].strftime('%Y/%m/%d %H:%M:%S'), chunk[-1]['datetime'].strftime('%H:%M:%S'))
        else:
            title = '{} - {}'.format(chunk[0]['datetime'].strftime('%Y/%m/%d %H:%M:%S'), chunk[-1]['datetime'].strftime('%Y/%m/%d %H:%M:%S'))
        for item in chunk:
            if item['ext'] == 'mp4':
                if item['type'].endswith('F'):
                    videos_f.append(item)
                elif item['type'].endswith('R'):
                    videos_r.append(item)
                else:
                    pass

        result = process_videos(options, time_start, time_end, 'F', videos_f, '{} Front'.format(title))
        if not result:
            break
        result = process_videos(options, time_start, time_end, 'R', videos_r, '{} Rear'.format(title))
        if not result:
            break

def process_videos(options, time_start, time_end, camera, videos, title):
    concat_filename = '{}-{}_{}.con'.format(time_start, time_end, camera)
    output_filename = '{}-{}_{}.mp4'.format(time_start, time_end, camera)
    upjob_filename = '{}-{}_{}.job'.format(time_start, time_end, camera)
    upload_filename = '{}-{}_{}.upl'.format(time_start, time_end, camera)
    playlist_filename = '{}-{}_{}.ply'.format(time_start, time_end, camera)

    if len(videos) <= options.concat_threshold:
        logger.info('{}, skipped (less than concat_threshold={})'.format(title, options.concat_threshold))
        return True

    create_concat_file(options.work_dir, concat_filename, videos, options.no_output, options.overwrite)

    create_output_file(options.work_dir, concat_filename, options.output_dir, output_filename, options.no_output, options.overwrite)

    return True

def create_concat_file(path, filename, videos, no_output, overwrite):
    if os.path.exists(os.path.join(path, filename)):
        if not overwrite:
            logger.info('{}, skipped (already exists)'.format(filename))
            return

    records = []
    md5_last_frame = None
    for video in videos:
        cmd = ['ffmpeg',
               '-nostats',
               '-hide_banner',
               '-i', os.path.join(video['dir'], video['filename']),
               '-an',
               '-f', 'framemd5',
               '-c', 'copy',
               '-']
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
        except Exception as e:
            logger.error('{} {} {} {} {}'.format(video['datetime'], video['type'], video['ext'], result.returncode, e))
            logger.error(result.stdout)
            logger.error(result.stderr)
            continue
        inpoint, tb_num, tb_den = 0, 1, 1
        for line in result.stdout.split('\n'):
            if line.startswith('#tb'):
                tb_num, tb_den = list(map(int, line.split()[-1].split('/')))
            elif not line.startswith('#') and len(line) > 0:
                splitted = line.split(',')
                md5, pts_time = splitted[-1].strip(), float(splitted[2]) * tb_num / tb_den
                if md5 == md5_last_frame:
                    inpoint = pts_time
        md5_last_frame = md5
        if result.returncode != 0:
            logger.warning('{} {} {} {} {}'.format(video['datetime'], video['type'], video['ext'], result.returncode, inpoint))
        else:
            logger.debug('{} {} {} {} {}'.format(video['datetime'], video['type'], video['ext'], result.returncode, inpoint))
        records.append((os.path.join(video['dir'], video['filename']), inpoint))

    if no_output:
        logger.info('{}, not created'.format(filename))
        return

    with open(os.path.join(path, filename), 'w') as f:
        for record in records:
            f.write("file '{}'\ninpoint {}\n".format(record[0], record[1]))

    logger.info('{}, created'.format(filename))

    return True

def create_output_file(path_work, concat_filename, path_output, output_filename, no_output, overwrite):

    if os.path.exists(os.path.join(path_output, output_filename)):
        if not overwrite:
            logger.info('{}, concat skipped (already exists)'.format(output_filename))
            return True

    if no_output:
        logger.info('{}, not created'.format(output_filename))
        return

    cmd = ['ffmpeg',
           '-fflags',
           '+genpts+igndts',
           '-f', 'concat',
           '-safe', '0',
           '-segment_time_metadata', '1',
           '-i', os.path.join(path_work, concat_filename),
           '-c:v', 'copy',
           '-af', 'aselect=concatdec_select,aresample=async=1',
           '-y', os.path.join(path_output, output_filename)]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
    except Exception as e:
        logger.error('error: {}'.format(e))
        logger.error('stdout: {}'.format(result.stdout))
        logger.error('stderr: {}'.format(result.stderr))

    if result.returncode != 0:
        logger.warning('{}, ended, returncode {}'.format(output_filename, result.returncode))
        return False

    logger.info('{}, created, returncode {}'.format(output_filename, result.returncode))

    return True

def cleanup(options):
    today_obj = datetime.date.today()
    cleanup_files(options.work_dir, PATTERN_WORKFILES, today_obj, options.retention)
    cleanup_files(options.output_dir, PATTERN_OUTPUTFILES, today_obj, options.retention)

def cleanup_files(directory, filepattern, today_obj, retention):
    files = sorted(os.listdir(directory))
    pattern = re.compile(filepattern)
    for f in files:
        if not os.path.isfile(os.path.join(directory, f)):
            continue
        matches = pattern.match(f)
        if not matches:
            continue
        datetime_obj = datetime.datetime.strptime(matches.group(1), '%Y%m%d_%H%M%S')
        date_obj = datetime_obj.date()
        if today_obj - date_obj <= datetime.timedelta(days=retention):
            continue
        logger.info('Deleting {}'.format(os.path.join(directory, f)))
        try:
            os.remove(os.path.join(directory, f))
        except Exception as e:
            logger.error('error: {}'.format(e))

def run(options):

    logger.debug('start')

    if not os.path.exists(options.source_dir):
        logger.error('source_dir {} not exists'.format(options.source_dir))
        sys.exit()

    if not os.path.exists(options.work_dir):
        logger.error('work_dir {} not exists'.format(options.work_dir))
        sys.exit()

    if not os.path.exists(options.output_dir):
        logger.error('output_dir {} not exists'.format(options.output_dir))
        sys.exit()

    chunks = create_chunks(options)
    result = process_chunks(options, chunks)
    cleanup(options)
    
if __name__ == "__main__":

    options = get_options()
    print('options: {}'.format(options))
    if not options:
        sys.exit()
    set_logging_level(options)

    lock = FileLock('{}.lock'.format(__file__))
    with lock:
        run(options)
