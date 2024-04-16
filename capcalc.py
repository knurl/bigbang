#! /usr/bin/env python

# map from pod name to container names
contsForPod: dict[str, list[str]] = {
        'operator': ['manager'],
        'cluster': ['hazelcast', 'sidecar-agent'],
        'manctr': ['management-center']
        }

# replicas per pod
def replicasPerPod(podname: str, numNodes: int) -> int:
    assert podname in contsForPod
    if podname == 'cluster':
        return numNodes
    else:
        return 1

def numberOfReplicas(numNodes: int) -> int:
    numReplicas = 0
    for podname in contsForPod:
        numReplicas += replicasPerPod(podname, numNodes)
    return numReplicas

def numberOfContainers(numNodes: int) -> int:
    # We start with the assumption that we have at least one node for the
    # coordinator, and one for each worker.
    assert numNodes >= 3
    numContainers = 0
    for podname, conts in contsForPod.items():
        numContainers += len(conts) * replicasPerPod(podname, numNodes)
    return numContainers
