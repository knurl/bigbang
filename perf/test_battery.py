#!python

import sys, os, json, re, pdb, time, threading, subprocess, select, signal
sys.path.append('..')
sys.path.append('../..')
from functools import reduce
import run, out, tpc
import pyjq
import csv
from collections import Counter

nworkers = 16
numloops = 1
filename_re = \
        re.compile(r'(tpcds_u\d\d?\d?_sf\d\d?\d?_\d\d?)_[\da-zA-Z]{6}\.csv')

def get_nodes():
    nodes = []
    nodesjson = json.loads(run.runCollect('kubectl get nodes -ojson'.split()))
    if nodesjson and len(nodesjson) > 0:
        nodes = pyjq.all('.items[] | select(.spec.taints|not) | '
                'select(.status.conditions[]?.reason=="KubeletReady" and '
                '.status.conditions[]?.status=="True") | .metadata.name',
                nodesjson)
    return nodes

def get_unready_pods():
    pods = []
    r = run.runTry(f'kubectl get pods -ojson'.split())
    if r.returncode == 0:
        podsjson = json.loads(r.stdout)
        if podsjson and len(podsjson) > 0:
            pods = pyjq.all('.items[] | '
            'select(.status.containerStatuses[]?.ready==false) |'
            '.metadata.name', podsjson)
    return pods

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
    d = Counter({k: numthreads for k in tpc.tpcds_queries})
    quality = sum(c.values())
    c.subtract(d)
    if reduce(lambda x, y: x or y, map(lambda x: x < 0, c.values())) == True:
        return (False, 0)
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
                    out.announce(f'INFERIOR {logfilename} '
                            f'(q {quality} < {best_quality})')
            else:
                if quality < 0:
                    found_error = True
                    found_error_file = logfilename
                    continue
                out.announce(f'INCOMPLETE {logfilename}')

    if found_error:
        raise ScalingError(f'{found_error_file} had ERRORS')

    return best_logfilename

# Returns the new 
def cluster_is_stable(nodes):
    assert nodes
    new_nodes = get_nodes()
    badpods = get_unready_pods()
    if nodes != new_nodes or len(new_nodes) - 1 != nworkers \
            or len(badpods) > 0:
        if nodes != new_nodes:
            print("Nodes have changed. Did we lose a spot instance?")
        if len(badpods) > 0:
            print("Bad pods: {}".format(badpods))
        return False
    return True

# We are unstable. Wait until we are stabilised
def wait_until_cluster_stable():
    print("Waiting for cluster to stabilise")
    goodruns = 0
    while True:
        time.sleep(30)
        badpods = get_unready_pods()
        if len(badpods) == 0 and nworkers == len(get_nodes()) - 1:
            goodruns += 1
        if goodruns >= 4:
            break
    print("Cluster seems to have stabilised")

logfile_dict = build_logfile_dict()

tests_to_run = []

#FIXME
#nodes = get_nodes() # Shouldn't change as long as we remain stable
#if not cluster_is_stable(nodes):
#    out.announceLoud(['Cluster lost stability', 'finding it again'])
#    wait_until_cluster_stable()
#    nodes = get_nodes()
#    out.announce(f'Cluster restabilised at {nworkers} workers')

for t in (1, 2, 4, 8, 16, 32, 64, 128):
    for s in ('sf1', 'sf10', 'sf100', 'sf200', 'sf400'):
        prefix = f'tpcds_u{t}_{s}_{nworkers}'
        uniq = out.randomString(6)
        filename = prefix + '_' + uniq + '.csv'

        # See if there is an existing logfile that we completed
        try:
            existing = get_best_existing_logfile(logfile_dict, prefix, t)
            if existing:
                avg = round(average_latency(existing))
                print(f'Test complete for {s}, t={t} in {existing} '
                        f'[average latency {avg}]')
                continue
        except ScalingError as e:
            out.announce(f'Avoid test for {s}, t={t}, because existing {e}')
            continue

        cmd = f'jmeter -n -JTHREADS={t} -JSCALESET={s} -JLOOPS={numloops} ' \
                f'-t run_tpcds.jmx -l {filename}'
        tests_to_run.append(cmd)

if tests_to_run:
    print('Tests to run:\n{}'.format("\n".join(tests_to_run)))
else:
    print('No tests to run!')

sys.exit(0)

while len(tests_to_run) > 0:
    cmd = tests_to_run.pop(0)
    out.announceBox(f'Running process as {cmd}')
    with subprocess.Popen(cmd.split(), stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, bufsize=1,
            preexec_fn=os.setsid) as p:
        now = time.time()
        polly = select.poll()
        polly.register(p.stdout, select.POLLIN)

        while p.poll() is None:
            if polly.poll(3):
                sys.stdout.write(p.stdout.readline())

            if time.time() - now < 15.0:
                continue
            now = time.time()

            # 15 seconds have passed since the last check. See if cluster
            # is still stable. If not, we need to kill the process.
            if not cluster_is_stable(nodes):
                tests_to_run.append(cmd)
                os.killpg(os.getpgid(p.pid), signal.SIGTERM)
                p.kill()
                out.announceLoud(['Cluster lost stability',
                    'terminating jmeter'])
                wait_until_cluster_stable()
                nodes = get_nodes()
                out.announce(f'Cluster restabilised at {nworkers} workers')
