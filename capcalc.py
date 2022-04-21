#!python

from run import runCollect
import os, sys, pdb, json, argparse
from collections import namedtuple
from tabulate import tabulate # type: ignore
from dataclasses import dataclass

kube = "kubectl"
tblfmt = "psql"

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
            tablefmt=tblfmt)

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
            return tabulate(rows, headers = hdr, tablefmt = tblfmt)
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

# map from pod name to container names
contsForPod: dict[str, list[str]] = {
        'coordinator': ['coordinator'],
        'worker': ['worker'],
        'hive': ['hive'],
        'ranger': ['ranger-usync', 'ranger-admin', 'ranger-db'],
        'cache-service': ['cache-service']
        }

# replicas per pod
def replicasPerPod(podname: str, numNodes: int) -> int:
    assert podname in contsForPod
    if podname == 'worker':
        return numNodes - 1
    else:
        return 1

def numberOfReplicas(numNodes: int) -> int:
    numReplicas = 0
    for podname in contsForPod:
        numReplicas += replicasPerPod(podname, numNodes)
    return numReplicas

# This function should be compared to planWorkerSize(), which also has an
# implicit count of the number of containers.
def numberOfContainers(numNodes: int) -> int:
    # We start with the assumption that we have at least one node for the
    # coordinator, and one for each worker.
    assert numNodes >= 2
    numContainers = 0
    for podname, conts in contsForPod.items():
        numContainers += len(conts) * replicasPerPod(podname, numNodes)
    return numContainers

class NodeResource:
    cpuleft: int
    memleft: int
    ContAlloc = namedtuple('ContAlloc', ['cname', 'cpu', 'mem'])
    pods: dict[str, list[ContAlloc]]

    def __init__(self, cpuleft, memleft):
        self.cpuleft = cpuleft
        self.memleft = memleft
        self.pods = {}

    def __repr__(self):
        return (f"{{cpuleft={self.cpuleft}, memleft={self.memleft} "
                f"pods={self.pods}}}")

    def canFit(self, cpu, mem):
        return self.cpuleft >= cpu and self.memleft >= mem

    def addPod(self, podname, contname, cpu, mem):
        assert self.canFit(cpu, mem)
        ca = self.ContAlloc(contname, cpu, mem)
        if podname not in self.pods:
            self.pods[podname] = [ca]
        else:
            self.pods[podname].append(ca)
        self.cpuleft -= cpu
        self.memleft -= mem

def allocateResources(namespace: str, verbose: bool,
        allocation: dict[str, float]) -> list[NodeResource]:
    nodeCount, c, m = getMinNodeResources(namespace, verbose)

    # Prepare a tracker of the amount of resource we have against all nodes
    nodeResources: list[NodeResource] = []
    for i in range(0, nodeCount):
        nodeResources.append(NodeResource(c, m))

    # These pods are never scheduled on same node
    antiAffinity = {'hive', 'ranger', 'cache-service'}

    for podname, fraction in allocation.items():
        numReplicas = replicasPerPod(podname, nodeCount)

        # For every replica for this pod...
        for i in range(0, numReplicas):
            # What are we allocating?
            cpu = int(c * fraction)
            mem = int(m * fraction)

            # Allocate the replica on first available node
            allocated = False
            for nr in nodeResources:
                # If this pod is already allocated to this node, skip
                if podname in nr.pods:
                    continue

                # If this pod is in the anti-affinity set, then skip if we find
                # any already-allocated pods in the same set
                if podname in antiAffinity:
                    if antiAffinity.intersection(nr.pods.keys()):
                        continue

                # If this node doesn't have sufficient resource, skip it
                if not nr.canFit(cpu, mem):
                    continue

                # We're Ok to allocate. Allocate all containers in pod
                cnames = contsForPod[podname]
                contcpu = int(cpu / len(cnames))
                contmem = int(mem / len(cnames))
                for cname in cnames:
                    nr.addPod(podname, cname, contcpu, contmem)
                # We allocated
                allocated = True
                break
            if not allocated:
                sys.exit(f"Failed to allocate replica {i} of {podname}")

    return nodeResources

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
    nodeResources: list[NodeResource] = allocateResources(namespace, verbose, {
        'coordinator': 3 / 4,
        'worker': 3 / 4,
        'hive': 1 / 4,
        'ranger': 1 / 4,
        'cache-service': 1 / 4
        })

    if verbose:
        # Attempt a possible scheduling of containers
        def makeTable(nodeResources, getleaf):
            cnames = [cn for contlist in contsForPod.values()
                    for cn in contlist]
            hdr = ["NODE"] + cnames + ["TOTAL"]
            nodenum = 1
            rows = []
            for nr in nodeResources:
                row = [nodenum]
                for cname in cnames:
                    amount = 0
                    for contallocs in nr.pods.values():
                        for ca in contallocs:
                            if ca.cname == cname:
                                amount = getleaf(ca)
                    row.append(amount)
                row.append(sum(row[1:])) # Add the TOTAL column
                rows.append(row)
            return tabulate(rows, headers = hdr, tablefmt = tblfmt)

        print("Possible distribution of CPU")
        print(makeTable(nodeResources, lambda x : x.cpu))
        print("Possible distribution of Memory")
        print(makeTable(nodeResources, lambda x : x.mem))

    cpu = {}
    mem = {}
    for nr in nodeResources:
        for contallocs in nr.pods.values():
            for ca in contallocs:
                cname = ca.cname.replace('-','_') # we're using in template
                cpu[cname] = ca.cpu
                mem[cname] = ca.mem

    # Convert format of our internal variables, ready to populate our templates
    env = {f"{k}_cpu": f"{v}m" for k, v in cpu.items()}
    env |= {f"{k}_mem": "{m}Mi".format(m = v >> 10) for k, v in mem.items()}
    env["workerCount"] = str(len(nodeResources) - 1)

    return env
