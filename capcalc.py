#! /usr/bin/env python

# map from pod name to container names
contsForPod: dict[str, list[str]] = {
        'operator': ['manager'],
        'cluster': ['hazelcast', 'sidecar-agent'],
        'manctr': ['management-center'],
        'bbclient': ['bbclient']
        }

# replicas per pod
def replicasPerPod(podname: str, numNodes: int, numClients: int) -> int:
    assert podname in contsForPod
    if podname == 'cluster':
        return numNodes
    elif podname == 'bbclient':
        return numClients
    else:
        return 1

def numberOfReplicas(numNodes: int, numClients: int) -> int:
    numReplicas = 0
    for podname in contsForPod:
        numReplicas += replicasPerPod(podname, numNodes, numClients)
    return numReplicas

def numberOfContainers(numNodes: int, numClients: int) -> int:
    assert numNodes >= 3
    numContainers = 0
    for podname, conts in contsForPod.items():
        numContainers += (len(conts) *
                          replicasPerPod(podname, numNodes, numClients))
    return numContainers
