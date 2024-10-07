package com.bbclient

import com.hazelcast.map.IMap

internal class SetRunnable(
    map: IMap<Int?, String?>,
    mapValueSize: Int,
    /*
     * synchronized
     */private var nextKey: Int
) : IMapMethodRunnable(map, "set", true) {
    private val value = "*".repeat(mapValueSize)

    @get:Synchronized
    var lastKey: Int
        private set

    @Synchronized
    private fun getNextKey(): Int {
        lastKey = nextKey
        nextKey++
        return lastKey
    }

    init {
        this.lastKey = this.nextKey
    }

    override fun invokeMethod() {
        map[getNextKey()] = value
    }
}
