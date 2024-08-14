#!/usr/bin/env python

class Containers:
    def __init__(self, contsForPod: dict[str, list[str]]):
        self.contsForPod = contsForPod

    def replicasPerPod(self,
                       podname: str,
                       numNodes: int,
                       numClients: int) -> int:
        return 1

    def numberOfReplicas(self, numNodes: int, numClients: int) -> int:
        numReplicas = 0
        for podname in self.contsForPod:
            numReplicas += self.replicasPerPod(podname, numNodes, numClients)
        return numReplicas

    def numberOfContainers(self, numNodes: int, numClients: int) -> int:
        assert numNodes >= 3
        numContainers = 0
        for podname, conts in self.contsForPod.items():
            numContainers += (len(conts) *
                              self.replicasPerPod(podname, numNodes, numClients))
        return numContainers

class HazelcastContainers(Containers):
    def __init__(self):
        contsForPod: dict[str, list[str]] = {
                'operator': ['manager'],
                'cluster': ['hazelcast', 'sidecar-agent'],
                'bbclient': ['bbclient']
                }
        super().__init__(contsForPod)

    # replicas per pod
    def replicasPerPod(self, podname: str, numNodes: int, numClients: int) -> int:
        assert podname in self.contsForPod
        if podname == 'cluster':
            return numNodes
        elif podname == 'bbclient':
            return numClients
        else:
            return 1

class ChaosMeshContainers(Containers):
    def __init__(self):
        contsForPod: dict[str, list[str]] = {
                'chaos-controller-manager': ['chaos-mesh'],
                'chaos-daemon': ['chaos-daemon'],
                'chaos-dashboard': ['chaos-dashboard'],
                'chaos-dns-server': ['chaos-dns-server']
                }
        super().__init__(contsForPod)

    def replicasPerPod(self, podname: str, numNodes: int, numClients: int) -> int:
        assert podname in self.contsForPod
        if podname == 'chaos-controller-manager':
            return min(numNodes, 3)
        elif podname == 'chaos-daemon':
            return numNodes
        else:
            return 1
