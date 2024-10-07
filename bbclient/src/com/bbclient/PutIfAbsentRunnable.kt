package com.bbclient

import com.hazelcast.map.IMap

internal class PutIfAbsentRunnable(
    map: IMap<Int?, String?>,
    mapValueSize: Int,
    private val firstKey: Int,
    private val lastKey: Int
) : IMapMethodRunnable(map, "putIfAbsent", false) {
    private val value = "*".repeat(mapValueSize)

    /*
     * synchronized
     */
    private var nextKey: Int

    @Synchronized
    private fun getNextKey(): Int {
        val nextKey = this.nextKey
        this.nextKey++
        if (this.nextKey == this.lastKey) this.nextKey = this.firstKey
        return nextKey
    }

    init {
        this.nextKey = firstKey
    }

    override fun invokeMethod() {
        checkNotNull(map.putIfAbsent(getNextKey(), value))
    }
}
