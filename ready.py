#import pdb
import json

# local imports
import run

def taints_are_ok(item: dict) -> bool:
    taint_ok = True

    if (spec := item.get('spec')) and (taints := spec.get('taints')):
        for taint in taints:
            if ((taintkey := taint.get('key')) and
                (taintvalue := taint.get('value')) and
                (tainteffect := taint.get('effect'))):
                if (taintkey != 'kubernetes.azure.com/scalesetpriority' or
                    taintvalue != 'spot' or
                    tainteffect != 'NoSchedule'):
                    taint_ok = False # found an unexpected bad taint

    return taint_ok

def get_nodes() -> tuple[set[str], set[str]]:
    ready_nodes: set[str] = set()
    all_nodes: set[str] = set()

    r = run.runTry("kubectl get nodes -ojson".split())
    if r.returncode != 0:
        return ready_nodes, all_nodes

    j = json.loads(r.stdout)
    if j is None or len(j) == 0:
        return ready_nodes, all_nodes

    if not (items := j.get('items')):
        return ready_nodes, all_nodes

    for item in items:
        metadata = item['metadata']
        name = metadata['name']
        assert len(name) > 0

        all_nodes.add(name) # add this node regardless of whether it's ready

        # Azure spot instances have specific taints used to ensure system pods
        # don't go onto spot instances. We also add tolerations for workers to
        # go onto spot instances. So these taints for Azure are Ok. For other
        # non-expected taints, don't count the node.
        if not taints_are_ok(item):
            continue # bad taint; don't count this item

        # If this node's Kubelet is ready, count it; otherwise skip
        if ((status := item.get('status')) and
            (conditions := status.get('conditions'))):
            for condition in conditions:
                if ((reason := condition.get('reason')) and 
                    (condstatus := condition.get('status')) and
                    reason == 'KubeletReady' and
                    condstatus == 'True'):
                    ready_nodes.add(name)
                    break

    return ready_nodes, all_nodes

def get_ready_nodes() -> set[str]:
    return get_nodes()[0]

def summarize_containers(namespace: str = "") -> tuple[set[str], set[str]]:
    namesp = f" --namespace {namespace}" if namespace else ""
    readyc: set[str] = set()
    allc: set[str] = set()

    try:
        j = json.loads(run.runCollect(f'kubectl{namesp} '
                                      'get pods -ojson'.split()))

        for item in j['items']:
            metadata = item['metadata']

            podname = metadata['name']
            assert len(podname) > 0

            # If we've asked for a specific ns, verify we've got that ns
            if (ns := metadata['namespace']) and namespace:
                assert ns == namespace

            # If this pod's containers are all ready, count it; otherwise skip
            css = item['status']['containerStatuses']

            for cs in css:
                cname = podname + '/' + cs['name']
                allc.add(cname)
                if cs['ready']:
                    readyc.add(cname)
    except Exception:
        pass

    return readyc, allc
