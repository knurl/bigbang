#! /usr/bin/env python

import sys, os, json, re, pdb, time, subprocess, select, signal, threading
import argparse, statistics
sys.path.append('..')
sys.path.append('../..')
from functools import reduce
import run, out, tpc, creds
import pyjq # type: ignore
import csv
from collections import Counter
from typing import IO

# 99.7% of values within a normal distribution lie within three standard
# deviations from the mean; 95% within two standard deviations; and 68% within
# one standard deviation
stddev_997pct = 3

numloops = 1

def prefix_regexp(nworkers: int) -> str:
    return r'(tpcds_u)(\d\d?\d?)(_)(sf\d\d?\d?)(_)' + f'({nworkers})'

def filename_regexp(nworkers: int) -> str:
    return prefix_regexp(nworkers) + r'_[\da-zA-Z]{6}\.csv'

def prefix_re(nworkers: int):
    return re.compile(prefix_regexp(nworkers))

def filename_re(nworkers: int):
    return re.compile(filename_regexp(nworkers))

testrun_re = re.compile(r'^(summary\s+=\s+)(\d+)(.*)$')
testrun_add_re = re.compile(r'^(summary\s+\+\s+)(\d+)(.*)$')

def get_nodes():
    ready_nodes = []

    r = run.runTry(f"kubectl get nodes -ojson".split())
    if r.returncode == 0:
        nodes = json.loads(r.stdout)
        if nodes and len(nodes) > 0:
            ready_nodes = pyjq.all('.items[] | select(.spec.taints|not) | '
                    'select(.status.conditions[]?.reason=="KubeletReady" and '
                    '.status.conditions[]?.status=="True") | .metadata.name',
                    nodes)
    return ready_nodes

def get_ready_pods():
    pods = []
    r = run.runTry(f'kubectl get pods -ojson'.split())
    if r.returncode == 0:
        podsjson = json.loads(r.stdout)
        if podsjson and len(podsjson) > 0:
            pods = pyjq.all('.items[] | '
            'select(.status.containerStatuses[]?.ready==true) |'
            '.metadata.name', podsjson)
    return pods

def build_logfile_dict(nworkers: int) -> dict[str, list[str]]:
    logfile_dict = {}
    for filename in filter(os.path.isfile, os.listdir()):
        mobj = filename_re(nworkers).match(filename)
        if mobj:
            prefix = ''.join(mobj.groups())
            if prefix not in logfile_dict:
                logfile_dict[prefix] = [filename]
            else:
                logfile_dict[prefix].append(filename)
    return logfile_dict

def logfile_completed(filename, numthreads):
    queries = []
    with open(filename) as csv_file:
        csv_reader = csv.DictReader(csv_file, delimiter=',')
        for row in csv_reader:
            rc = row.get('responseCode')
            rm = row.get('responseMessage')
            if rc and rc == '200' and rm and rm == 'OK':
                queries.append(row['label'])
            # query error, probably from overload; don't try it again
            elif rc and rm and rc != 'null 0':
                return (False, -1.0)
    needed_tests = len(tpc.tpcds_queries) * numthreads
    c = Counter(queries)
    quality: float = float(sum(c.values())) / float(needed_tests)
    return (quality >= 1.0, quality)

def average_latency(filenames: list[str]) -> float:
    response_times = []
    for filename in filenames:
        with open(filename) as csv_file:
            csv_reader = csv.DictReader(csv_file, delimiter=',')
            for row in csv_reader:
                if (row['responseCode'] == '200' and
                        row['responseMessage'] == 'OK'):
                    response_times.append(float(row['elapsed']))

    mean = statistics.mean(response_times)

    # include everything within 95% of data (assuming a normal distribution)
    cutoff = stddev_997pct * statistics.stdev(response_times)

    outliers = list(filter(lambda x: abs(x - mean) > abs(cutoff - mean),
                           response_times))
    nrt = len(response_times)
    within = round((nrt - len(outliers)) * 100.0 / float(nrt), 1)
    if within > 99.7:
        print('WARNING: In calculating mean {m} for file {f}, {w}% of data '
              'were within 3*stddev vs 99.7% expected for normal '
              'distribution'.format(m=mean, f=filename, w=within))

    return mean

class QueryErrorException(Exception):
    pass

def get_best_existing_logfile(logfile_dict, prefix, numthreads) -> list[str]:
    logfilenames = logfile_dict.get(prefix)
    best_logfiles: list[str] = []
    best_quality = 0.0

    if logfilenames:
        for logfilename in logfilenames:
            completed, quality = logfile_completed(logfilename, numthreads)
            if not completed:
                if quality < 0.0:
                    out.announce(f'QUERY ERROR {logfilename}')
                    raise QueryErrorException(f'Query error in {logfilename}')

                out.announce('INCOMPLETE {fn}, q={q}%'.format(fn = logfilename,
                  q = round(quality*100, 2)))
            else:
                if quality >= best_quality:
                    best_quality = quality
                    best_logfiles.append(logfilename)
                else:
                    out.announce(f'INFERIOR {logfilename} '
                            f'(q {quality} < {best_quality})')

    return best_logfiles

# Returns the new 
def cluster_is_stable(nworkers: int, old_nodes):
    exp_nnodes = nworkers + 1

    if not old_nodes or len(old_nodes) < 3:
        print('Snapshot of node state looks corrupt!')
        return False

    new_nodes = get_nodes()
    if old_nodes != new_nodes:
        print('Nodes have changed. Did we lose a spot instance?')
        return False

    if len(new_nodes) != exp_nnodes:
        print('Expected {x} nodes but only see {n}'.format(x=exp_nnodes,
                                                           n=len(new_nodes)))
        return False

    goodpods = get_ready_pods()
    if len(goodpods) != exp_nnodes:
        print('Expected {p} ready pods but see {n}'.format(p=exp_nnodes,
                                                           n=len(goodpods)))
        return False

    return True

# We are unstable. Wait until we are stabilised
def wait_until_cluster_stable(nworkers: int):
    print("Waiting for cluster to stabilise")
    exp_nnodes = nworkers + 1
    goodruns = 0
    while True:
        time.sleep(30)
        goodpods = get_ready_pods()
        if len(goodpods) == exp_nnodes and len(get_nodes()) == exp_nnodes:
            goodruns += 1
        if goodruns >= 4:
            break
    print("Cluster seems to have stabilised")

def send_email(address, body):
    rc = subprocess.run(['/usr/bin/mail', '-s', 'test_battery status',
        address], text=True, input=body)
    if rc.returncode != 0:
        print('Failed to send status mail')

def main():
    parser = argparse.ArgumentParser(description="Run test battery")
    parser.add_argument('nworkers', type=int,
                   help='How many workers are running in cluster?')
    parser.add_argument('-n', '--analyse-only', action='store_true',
                        help='Analyse only, and do not run')
    parser.add_argument('-m', '--mail-status', action='store', type=str,
                        metavar='email_address',
                        help='Email status to specified address')
    parser.add_argument('-r', '--redo', action='store', nargs='+',
                        dest='tests_to_redo', default=[],
                        help='Provide prefix for tests to redo')
    parser.add_argument('-c', '--renew-creds', action='store_true',
                        help='Renew credentials and quit.')
    ns = parser.parse_args()
    nworkers = ns.nworkers

    if ns.renew_creds:
        creds.renew_creds_sync()
        sys.exit(0)

    def generate_cmd(t, s, nl) -> str:
        uniq = out.randomString(6)
        fn = f'tpcds_u{t}_{s}_{nworkers}_{uniq}.csv'
        cmd = (f'jmeter -n -JTHREADS={t} -JSCALESET={s} -JLOOPS={nl} -t '
                f'run_tpcds.jmx -l {fn}')
        return cmd

    logfile_dict = build_logfile_dict(nworkers)

    tests_to_run: list[tuple[int, str]] = []
    tests_to_redo_pfx: list[str] = ns.tests_to_redo

    for prefix in tests_to_redo_pfx:
        mobj = prefix_re(nworkers).match(prefix)
        if not mobj:
            sys.exit('Prefix {} is not of correct format'
                     '{}'.format(prefix, prefix_regexp(nworkers)))
        groups = mobj.groups()
        if len(groups) != 6:
            sys.exit('Prefix {} is not of correct format'
                     '{}'.format(prefix, prefix_regexp(nworkers)))
        threads = int(groups[1])
        scaleset = groups[3]
        testcount = len(tpc.tpcds_queries)*threads*numloops
        cmd = generate_cmd(t=threads, s=scaleset, nl=numloops)
        tests_to_run.append((testcount, cmd))

    nodes = []

    if not ns.analyse_only:
        nodes = get_nodes() # Shouldn't change as long as we remain stable
        if not cluster_is_stable(nworkers, nodes):
            out.announceLoud(['Cluster lost stability', 'finding it again'])
            wait_until_cluster_stable(nworkers)
            nodes = get_nodes()
            out.announce(f'Cluster restabilised at {nworkers} workers')

    for s in ('sf1', 'sf10', 'sf100', 'sf200', 'sf400'):
        for t in (1, 2, 4, 8, 16, 32, 64, 128):
            prefix = f'tpcds_u{t}_{s}_{nworkers}'

            # Avoid double-counting, if we've already specified that tests for
            # specified prefixes need to be redone
            if prefix in tests_to_redo_pfx:
                continue

            # See if there is an existing logfile that we completed
            try:
                existing = get_best_existing_logfile(logfile_dict, prefix, t)
                if not existing:
                    tests_to_run.append((len(tpc.tpcds_queries)*t*numloops,
                        generate_cmd(t, s, numloops)))
                else:
                    avg = round(average_latency(existing))
                    print('Test complete for {s}, t={t} in {existing} '
                          '[average latency {avg}]'.format(s=s, t=t,
                                                           existing=existing,
                                                           avg=avg))
            except QueryErrorException as e:
                print(f'Avoiding test: {e}')

    if tests_to_run:
        t2r = [x[1] for x in tests_to_run]
        print('{n} tests to run:\n{t}'.format(n=len(t2r), t="\n".join(t2r)))
    else:
        print('No tests to run!')

    if ns.analyse_only:
        sys.exit(0)

    heartbeat_timer = time.time()
    heartbeat_timeout = 3600.0 # every hour
    cluster_stable_timer = time.time()
    cluster_stable_timeout = 60.0 # every two minutes
    creds_timer = time.time()
    creds_timeout = 3600.0*4
    sent_email = False

    def email_status_update(msg: str, results: list[str]) -> None:
        nonlocal ns, tests_to_run, sent_email
        num_to_show = 5
        if not ns.mail_status:
            return
        body = f'{msg}\n\n'
        if len(results) >= num_to_show:
            body += ('Latest test results are: ' +
                    ''.join(results[-num_to_show:]) + '\n')
        t2r = [x[1] for x in tests_to_run]
        if t2r:
            body += '{} tests left to run:\n'.format(len(t2r))
            body += '\n'.join(t2r) + '\n'
        else:
            body += 'No tests remaining.\n'
        send_email(ns.mail_status, body)
        sent_email = True

    while len(tests_to_run) > 0:
        testcount, cmd = tests_to_run.pop(0)
        out.announceBox(f'Running process as {cmd}')
        cmd_output = []
        with subprocess.Popen(cmd.split(), stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, bufsize=1,
                preexec_fn=os.setsid) as p:
            assert p.stdout is not None
            stdout: IO[str] = p.stdout
            polly = select.poll()
            polly.register(stdout.fileno(), select.POLLIN)

            while p.poll() is None:
                if polly.poll(3):
                    line = stdout.readline()
                    status = ''
                    m = testrun_re.match(line)
                    m_add = testrun_add_re.match(line)
                    if m:
                        denom = str(testcount)
                        numer = m.group(2).rjust(len(denom))
                        status = '{}/{} {}'.format(numer, denom, m.group(3))
                    elif not m_add:
                        status = line[:-1] # strip newline
                    if status:
                        if sent_email:
                            status += ' [X]\n'
                            sent_email = False
                        else:
                            status += '\n'
                        cmd_output.append(status)
                        sys.stdout.write(status)

                if time.time() - heartbeat_timer >= heartbeat_timeout:
                    # Heartbeat timer expired. Reset and send status
                    heartbeat_timer = time.time() # reset timer
                    email_status_update(f'Still running: {cmd}', cmd_output)

                if time.time() - creds_timer >= creds_timeout:
                    # Credentials timer expired. Reset and renew creds
                    creds_timer = time.time() # reset timer
                    creds.renew_creds_async()

                if time.time() - cluster_stable_timer >= cluster_stable_timeout:
                    # Cluster stability timer expired. See if cluster is still
                    # stable. If not, we need to kill the process.
                    cluster_stable_timer = time.time() # reset timer

                    if not cluster_is_stable(nworkers, nodes):
                        unstable_time = time.time()

                        # suspend the jmeter process for now
                        p.send_signal(signal.SIGSTOP)
                        msg = f'Suspended test {cmd}'
                        out.announce(msg)
                        email_status_update(msg, cmd_output)

                        out.announceLoud(['Cluster lost stability',
                            'temporarily pausing jmeter'])
                        wait_until_cluster_stable(nworkers)
                        nodes = get_nodes()
                        elapsed_time = time.time() - unstable_time
                        msg1 = (f'Cluster restabilised at {nworkers} workers'
                                f'after {elapsed_time}s')
                        out.announce(msg1)

                        # restart jmeter process
                        p.send_signal(signal.SIGCONT) 
                        msg2 = f'Continuing test {cmd}'
                        out.announce(msg2)
                        email_status_update(f'{msg1}\n{msg2}', cmd_output)
                        continue

        email_status_update(f'Just completed: {cmd}', cmd_output)

    if ns.mail_status:
        send_email(ns.mail_status, "All tests are now complete.")
                    
if __name__ == '__main__':
    main()
