#!python

from run import runCollect
import os, sys, pdb, json, argparse
from collections import namedtuple
from tabulate import tabulate

kube = "kubectl"

def json2str(jsondict: dict) -> str:
    return json.dumps(jsondict, indent=4, sort_keys=True)

# Normalise CPU to 1000ths of a CPU ("mCPU")
def normaliseCpu(cpu) -> int:
    if cpu.endswith("m"):
        cpu = cpu[:-1]
        assert cpu.isdigit()
        cpu = int(cpu)
    else:
        assert cpu.isdigit()
        cpu = int(cpu) * 1000
    return cpu

# Normalise memory to Ki
def normaliseMem(mem) -> int:
    normalise = { "Ki": 0, "Mi": 10, "Gi": 20 }
    assert len(mem) > 2
    unit = mem[-2:]
    assert unit.isalpha()
    assert unit in normalise
    mem = mem[:-2]
    assert mem.isdigit()
    mem = int(mem)
    mem <<= normalise[unit]
    return mem

def getMinNodeResources(namespace: str, verbose: bool = False) -> tuple:
    nodes = json.loads(runCollect(f"{kube} get nodes -o "
        "json".split()))["items"]
    pods = json.loads(runCollect(f"{kube} get pods -A -o "
        "json".split()))["items"]
    def dumpNodesAndPods() -> None:
        print(json2str(nodes))
        print(json2str(pods))

    # First, we need a tracker of resource left on each node after deducting
    # system pod resource consumption.
    allocatable = {t["metadata"]["name"]: {"cpu":
        normaliseCpu(t["status"]["allocatable"]["cpu"]), "mem":
        normaliseMem(t["status"]["allocatable"]["memory"])} for t in nodes}
    nodeCount = len(allocatable)
    # Next, we'll track the resource of any Starburst pods we see running
    sbcpu: dict[str, dict[str, int]] = {}
    sbmem: dict[str, dict[str, int]] = {}

    def accountSbCpu(nn: str, cn: str, cpu: int):
        if nn not in sbcpu: sbcpu[nn] = {}
        sbcpu[nn][cn] = cpu

    def accountSbMem(nn: str, cn: str, mem: int):
        if nn not in sbmem: sbmem[nn] = {}
        sbmem[nn][cn] = mem

    def ddict2tab():
        return tabulate([(k, v["cpu"], v["mem"])
            for k, v in allocatable.items()],
            headers = ["NODE", "AVAIL CPU", "AVAIL MEM"],
            tablefmt="fancy_grid")

    if verbose:
        print("Raw allocatable")
        print(ddict2tab())

    # Grab the list of resource requests for every container
    Request = namedtuple('Request', ['ns', 'node', 'cname', 'cpu', 'mem'])
    creq: list[Request] = []
    for p in pods:
        spec = p["spec"]
        nodename = spec["nodeName"] if "nodeName" in spec else "unallocated"
        for c in p["spec"]["containers"]:
            if "requests" in c["resources"]:
                req = c['resources']['requests']
                cpu = normaliseCpu(req['cpu']) if 'cpu' in req else 0
                mem = normaliseMem(req['memory']) if 'memory' in req else 0
                creq.append(Request(ns = p['metadata']['namespace'],
                    node = nodename, cname = c['name'], cpu = cpu, mem = mem))

    # Now separate into Starburst and non-Starburst
    sbcreq: list[Request] = []
    k8creq: list[Request] = []
    for x in creq:
        (k8creq, sbcreq)[x.ns == namespace].append(x)

    for r in k8creq:
        try:
            an = allocatable[r.node]
        except:
            print(f"{r.node} should be in {allocatable}")
            dumpNodesAndPods()
            raise
        an["cpu"] -= r.cpu
        an["mem"] -= r.mem

    for r in sbcreq:
        accountSbCpu(r.node, r.cname, r.cpu)
        accountSbMem(r.node, r.cname, r.mem)

    if verbose:
        print("Raw allocatable after system pods")
        print(ddict2tab())
        cnames = sorted(list(set(map(lambda x: x.cname, sbcreq))))
        hdr = ['NODE'] + cnames + ['USED', 'REMAINING']
        def makeTable(d, key):
            rows = []
            nnames = sorted(d.keys())
            for node in nnames:
                containers = d[node]
                row = [node]
                for cname in cnames:
                    if cname in containers:
                        row.append(containers[cname])
                    else:
                        row.append(0)
                used = sum(row[1:])
                if node in allocatable:
                    remaining = str(allocatable[node][key] - used)
                else:
                    remaining = "n/a"
                row += [used, remaining]
                rows.append(row)
            return tabulate(rows, headers = hdr, tablefmt = "fancy_grid")
        print("Current Starburst CPU resource usage")
        print(makeTable(sbcpu, 'cpu'))
        print("Current Starburst memory resource usage")
        print(makeTable(sbmem, 'mem'))

    mincpu = min([x["cpu"] for x in allocatable.values()])
    minmem = min([x["mem"] for x in allocatable.values()])
    assert mincpu > 0 and minmem > 0
    print("All nodes have >= {c}m CPU and {m}Ki mem after K8S "
            "system pods".format(c = mincpu, m = minmem))
    return nodeCount, mincpu, minmem

# planWorkerSize works out the minimum amount of CPU and memory on every node,
# across the cluster (via a helper function), then apportions this resource out
# across the known containers.
#
# Strategy: Each worker or coordinator gets 7/8 of the resource on each node
# (after resources for K8S system pods are removed). We put the coordinator and
# workers all on different nodes, which means every node has a remaining 1/8
# capacity. We reserve this for Ranger, Hive, and we also leave 1/8 so that we
# can do rolling upgrades ot Ranger or Hive (by requiring that nodeCount > 2).
# We guarantee that Ranger and Hive will be scheduled to different nodes by
# using pod anti-affinity rules.
#
def planWorkerSize(namespace: str, verbose: bool = False) -> dict:
    nodeCount, c, m = getMinNodeResources(namespace, verbose)
    cpu = {}
    mem = {}

    # 7/8 for coordinator and workers
    cpu["worker"] = cpu["coordinator"] = (c >> 3) * 7
    mem["worker"] = mem["coordinator"] = (m >> 3) * 7
    print("Workers & coordinator get {c}m CPU and {m}Mi mem".format(c =
        cpu["worker"], m = mem["worker"] >> 10))

    # Hive - one container, gets 1/8
    hivecpu = cpu["hive"] = c >> 3
    hivemem = mem["hive"] = m >> 3
    assert cpu["worker"] + hivecpu <= c
    assert mem["worker"] + hivemem <= m
    print("hive total resources: {c}m CPU and {m}Mi mem".format(c = hivecpu, m
        = hivemem))
    print("hive gets {c}m CPU and {m}Mi mem".format(c = cpu["hive"],
        m = mem["hive"] >> 10))

    # Ranger - admin gets 2/32, db and usync each get 1/32
    cpu["ranger_usync"] = cpu["ranger_db"] = c >> 5
    cpu["ranger_admin"] = c >> 4
    mem["ranger_usync"] = mem["ranger_db"] = m >> 5
    mem["ranger_admin"] = m >> 4
    rangercpu = cpu["ranger_admin"] + cpu["ranger_db"] + cpu["ranger_usync"]
    rangermem = mem["ranger_admin"] + mem["ranger_db"] + mem["ranger_usync"]
    assert cpu["worker"] + rangercpu <= c
    assert mem["worker"] + rangermem <= m
    print("ranger total resources: {c}m CPU and {m}Mi mem".format(c =
        rangercpu, m = rangermem))
    print("ranger-usync and -db get {c}m CPU and {m}Mi mem".format(c =
        cpu["ranger_usync"], m = mem["ranger_usync"] >> 10))
    print("ranger-admin gets {c}m CPU and {m}Mi mem".format(c =
        cpu["ranger_admin"], m = mem["ranger_admin"] >> 10))

    # Convert format of our internal variables, ready to populate our templates
    env = {f"{k}_cpu": f"{v}m" for k, v in cpu.items()}
    env |= {f"{k}_mem": "{m}Mi".format(m = v >> 10) for k, v in
        mem.items()}

    if verbose:
        # Attempt a possible scheduling of containers
        def makeTable(d):
            cs = d.keys()
            hdr = ["NODE"] + list(cs) + ["TOTAL"]
            # Coordinator - row 1
            rows = []
            rows.append([1] + [d[c] if c in ("coordinator", "hive") else 0 for
                c in cs])
            rows.append([2] + [d[c] if c in ("worker", "ranger_admin",
                "ranger_db", "ranger_usync") else 0 for c in cs])
            while len(rows) < nodeCount:
                rows.append([len(rows) + 1] + [d[c] if c == "worker" else 0 for
                    c in cs])
            for r in rows:
                r.append(sum(r[1:]))
            return tabulate(rows, headers = hdr, tablefmt = "fancy_grid")

        print("Possible distribution of CPU")
        print(makeTable(cpu))
        print("Possible distribution of Memory")
        print(makeTable(mem))

    env["workerCount"] = str(nodeCount - 1)
    return env
