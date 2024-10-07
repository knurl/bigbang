package com.bbclient

import com.hazelcast.map.IMap

internal class IsEmptyRunnable(map: IMap<Int?, String?>) : IMapMethodRunnable(map, "isEmpty", false) {
    override fun invokeMethod() { // ignore newValue
        val isEmpty = map.isEmpty
        assert(!isEmpty)
    }
}
