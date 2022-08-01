#!python

import sys, os, json, re, pdb, time, threading, subprocess, select, signal
import csv, argparse
sys.path.append('..')
sys.path.append('../..')
from test_harness import build_logfile_dict, get_best_existing_logfile, \
        average_latency
import test_harness
import run, out, tpc
import pyjq # type: ignore
from collections import Counter

numloops=1

logfile_dict = build_logfile_dict()

concur_l = 'Concurrency'
sizes = (1, 10, 100, 200, 400)
sizes_str = list(map(str, sizes))
numthreadcount = 8
threads = list(map(lambda x: 2**x, range(numthreadcount)))

def get_most_recent(filenames: list[str]) -> str:
    most_recent_mtime = 0.0
    most_recent_file = ''
    for filename in filenames:
        mtime = os.path.getmtime(filename)
        if not most_recent_mtime or mtime > most_recent_mtime:
            most_recent_mtime = mtime
            most_recent_file = filename
    assert most_recent_file
    return most_recent_file

def main() -> None:
    p = argparse.ArgumentParser(description="Run test battery")
    p.add_argument('-r', '--recent', action='store_true',
            help='If there are multiple logs, prefer most recent.')
    ns = p.parse_args()
    for nworkers in (4, 8, 16):
        # Write a separate file for each scale set
        with open(f'avglatency_{nworkers}.csv', 'w', newline='') as outf:
            headers = [concur_l] + sizes_str
            csv_writer = csv.DictWriter(outf, fieldnames=headers,
                    delimiter=',')
            csv_writer.writeheader()

            # Write a row
            for t in threads:
                # Fill in the columns in the row
                row = {concur_l: t}
                for size in (1, 10, 100, 200, 400):
                    s = f'sf{size}'
                    pfx = f'tpcds_u{t}_{s}_{nworkers}'
                    avg = 'NULL'

                    # See if there is an existing logfile that we completed
                    existing = get_best_existing_logfile(logfile_dict, pfx, t)
                    if len(existing) > 1 and ns.recent:
                        most_recent = get_most_recent(existing)
                        avg = str(round(average_latency([most_recent])))
                    if existing:
                        avg = str(round(average_latency(existing)))
                    row[str(size)] = avg

                csv_writer.writerow(row)

if __name__ == '__main__':
    main()
