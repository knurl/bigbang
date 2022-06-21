#!python

import sys, os, json, re, pdb, time, threading, subprocess, select, signal
sys.path.append('..')
sys.path.append('../..')
import run, out, tpc
import pyjq
import csv
from collections import Counter

numloops=1
filename_re = \
        re.compile(r'(tpcds_u\d\d?\d?_sf\d\d?\d?_\d\d?)_[\da-zA-Z]{6}\.csv')

def build_logfile_dict():
    logfile_dict = {}
    for filename in filter(os.path.isfile, os.listdir()):
        mobj = filename_re.match(filename)
        if mobj:
            k = mobj.group(1)
            if k not in logfile_dict:
                logfile_dict[k] = [filename]
            else:
                logfile_dict[k].append(filename)
    return logfile_dict

def logfile_completed(filename, numthreads):
    queries = []
    with open(filename) as csv_file:
        csv_reader = csv.DictReader(csv_file, delimiter=',')
        for row in csv_reader:
            if row['responseCode'] == '200' and row['responseMessage'] == 'OK':
                queries.append(row['label'])
            else:
                return (False, -1)
                break
    c = Counter(queries)
    numruns = numloops * numthreads
    quality = 0
    for query, count in c.items():
        if count < numruns:
            return (False, 0)
        quality += count
    return (True, quality)

def average_latency(filename):
    response_times = []
    with open(filename) as csv_file:
        csv_reader = csv.DictReader(csv_file, delimiter=',')
        for row in csv_reader:
            if row['responseCode'] == '200' and row['responseMessage'] == 'OK':
                response_times.append(float(row['elapsed']))
    return sum(response_times) / len(response_times)

class ScalingError(Exception):
    pass

def get_best_existing_logfile(logfile_dict, prefix, numthreads):
    best_logfilename = None
    best_quality = 0
    found_error = False
    found_error_file = None

    logfilenames = logfile_dict.get(prefix)

    if logfilenames:
        for logfilename in logfilenames:
            completed, quality = logfile_completed(logfilename, numthreads)
            if completed:
                if quality > best_quality:
                    best_logfilename = logfilename
                    best_quality = quality
                else:
                    out.announce(f'DELETE {logfilename} '
                            f'(q {quality} < {best_quality})')
            else:
                if quality < 0:
                    found_error = True
                    found_error_file = logfilename
                    continue
                out.announce(f'DELETE {logfilename} (incomplete)')

    if found_error:
        raise ScalingError(f'logfile {found_error_file} had ERRORS')

    return best_logfilename

logfile_dict = build_logfile_dict()

tests_to_run = []

concur_l = 'Concurrency'
sizes = (1, 10, 100, 200, 400)
sizes_str = list(map(str, sizes))
numthreadcount = 8
threads = list(map(lambda x: 2**x, range(numthreadcount)))

for nworkers in (4, 8, 16):
    # Write a separate file for each scale set
    with open(f'avglatency_{nworkers}.csv', 'w', newline='') as outf:
        headers = [concur_l] + sizes_str
        csv_writer = csv.DictWriter(outf, fieldnames=headers, delimiter=',')
        csv_writer.writeheader()

        # Write a row
        for t in threads:
            # Fill in the columns in the row
            row = {concur_l: t}
            for size in (1, 10, 100, 200, 400):
                s = f'sf{size}'
                prefix = f'tpcds_u{t}_{s}_{nworkers}'
                avg = 'NULL'

                # See if there is an existing logfile that we completed
                try:
                    existing = get_best_existing_logfile(logfile_dict, prefix, t)
                    if existing:
                        avg = round(average_latency(existing))
                except ScalingError as e:
                    pass

                row[str(size)] = avg

            csv_writer.writerow(row)
