package com.bbclient

import com.hazelcast.cluster.Cluster
import com.hazelcast.config.Config
import com.hazelcast.core.Hazelcast
import com.hazelcast.core.HazelcastInstance

class EmbeddedHazelcastCluster internal constructor(numNodes: Int) {
    private var memberList: MutableList<HazelcastInstance> = ArrayList()

    init {
        val memberConfig = Config()
        memberConfig.setClusterName("embedded")
        val networkConfig = memberConfig.networkConfig
        val tcpIpConfig = networkConfig.join.tcpIpConfig
        tcpIpConfig.setEnabled(true)
        var port = 5701
        for (i in 0 until numNodes) {
            tcpIpConfig.addMember("127.0.0.1:" + port++.toString())
        }
        for (i in 0 until numNodes) memberList.add(Hazelcast.newHazelcastInstance(memberConfig))
    }

    fun getInstance(index: Int): HazelcastInstance {
        return memberList[index]
    }

    val cluster: Cluster
        get() = memberList[0].cluster
}
