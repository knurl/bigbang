package com.bbclient;

import com.hazelcast.map.IMap;

class PutIfAbsentRunnable extends IMapMethodRunnable {
    private final String value;

    private final int firstKey;
    private final int lastKey;

    /*
     * synchronized
     */
    private int nextKey;

    private synchronized int getNextKey() {
        var nextKey = this.nextKey;
        this.nextKey++;
        if (this.nextKey == this.lastKey)
            this.nextKey = this.firstKey;
        return nextKey;
    }

    PutIfAbsentRunnable(IMap<Integer, String> map,
                        int mapValueSize,
                        int firstKey,
                        int lastKey) {
        super(map, "putIfAbsent", false);
        this.value = "*".repeat(mapValueSize);
        this.firstKey = firstKey;
        this.lastKey = lastKey;
        this.nextKey = firstKey;
    }

    void invokeMethod() {
        var oldValue = map.putIfAbsent(getNextKey(), value);
        /* We always use keys we've used before! */
        assert (oldValue != null);
    }
}
