package com.bbclient;

import com.hazelcast.map.IMap;

class IsEmptyRunnable extends IMapMethodRunnable {
    IsEmptyRunnable(IMap<Long, String> map) {
        super(map,"isEmpty", false);
    }

    void invokeMethod() { // ignore newValue
        var isEmpty = map.isEmpty();
        assert(!isEmpty);
    }
}
