#! /usr/bin/env python

import sys, os, json, re, pdb, time, threading, subprocess, select, signal
import csv, argparse
sys.path.append('..')
sys.path.append('../..')
from test_harness import build_logfile_dict, get_best_existing_logfile, \
        average_latency
import test_harness
import run, out, tpc
from collections import Counter

numloops=1

concur_l = 'Concurrency'
sizes = (1, 10, 100, 200, 400)
sizes_str = list(map(str, sizes))

# All threadcounts between 1 and 128, inclusive
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
            help=('If there are multiple valid logs for a given test prefix, '
                  'prefer most recent.'))
    ns = p.parse_args()
    use_recent = ns.recent
    for nworkers in (4, 8, 16):
        logfile_dict = build_logfile_dict(nworkers)

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
                    pfx = f'tpcds_u{t}_sf{size}_{nworkers}'
                    avg = 'NULL'

                    # See if there is an existing logfile that we completed
                    try:
                        existing = get_best_existing_logfile(logfile_dict,
                                                             pfx,
                                                             t)

                        # If there are multiple suitable logfiles, and the user
                        # has requested that we use only the most recent ones,
                        # then retrieve the most recent logfiles from the
                        # returned list of suitable logfiles.
                        if len(existing) > 1 and use_recent:
                            most_recent = get_most_recent(existing)
                            avg = str(round(average_latency([most_recent])))
                        elif existing:
                            avg = str(round(average_latency(existing)))
                    except test_harness.QueryErrorException as e:
                        # Unrecoverable query error; don't try again
                        pass

                    row[str(size)] = avg

                csv_writer.writerow(row)

if __name__ == '__main__':
    main()
