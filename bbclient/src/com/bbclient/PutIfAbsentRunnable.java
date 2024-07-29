package com.bbclient;

import com.hazelcast.map.IMap;

import static com.bbclient.RandomStringBuilder.generateRandomString;

class PutIfAbsentRunnable extends IMapMethodRunnable {
    private final String value;

    private final long firstKey;
    private final long lastKey;

    /*
     * synchronized
     */
    private long nextKey;

    private synchronized long getNextKey() {
        var nextKey = this.nextKey;
        this.nextKey++;
        if (this.nextKey > this.lastKey)
            this.nextKey = this.firstKey;
        return nextKey;
    }

    PutIfAbsentRunnable(IMap<Long, String> map,
                        int mapValueSize,
                        long firstKey,
                        long lastKey) {
        super(map, "putIfAbsent", false);
        this.value = generateRandomString(mapValueSize);
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
