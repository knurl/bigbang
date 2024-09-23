package com.bbclient;

import com.hazelcast.cluster.Cluster;
import com.hazelcast.config.Config;
import com.hazelcast.config.NetworkConfig;
import com.hazelcast.core.Hazelcast;
import com.hazelcast.core.HazelcastInstance;

import java.util.ArrayList;
import java.util.List;

public class EmbeddedHazelcastCluster {
    List<HazelcastInstance> memberList = new ArrayList<>();

    EmbeddedHazelcastCluster(int numNodes) {
        Config memberConfig = new Config();
        memberConfig.setClusterName("embedded");
        NetworkConfig networkConfig = memberConfig.getNetworkConfig();
        var tcpIpConfig = networkConfig.getJoin().getTcpIpConfig();
        tcpIpConfig.setEnabled(true);
        var port = 5701;
        for (var i = 0; i < numNodes; i++) {
            tcpIpConfig.addMember("127.0.0.1:" + String.valueOf(port++));
        }
        for (var i = 0; i < numNodes; i++)
            memberList.add(Hazelcast.newHazelcastInstance(memberConfig));
    }

    public HazelcastInstance getInstance(int index) {
        return memberList.get(index);
    }

    public Cluster getCluster() {
        return memberList.getFirst().getCluster();
    }
}
