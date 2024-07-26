package com.bbclient;

import com.hazelcast.map.IMap;

public class IsEmptyRunnable extends IMapMethodRunnable {
    IsEmptyRunnable(IMap<Long, String> map) {
        super(map,"isEmpty");
    }

    void invokeMethod(String newValue) { // ignore newValue
        var isEmpty = super.map.isEmpty();
        assert(!isEmpty);
    }
}
