package com.bbclient;

import com.hazelcast.map.IMap;

import static com.bbclient.RandomStringBuilder.generateRandomString;

class SetRunnable extends IMapMethodRunnable {
    private final String value;

    /*
     * synchronized
     */
    private long nextKey;
    private long lastKey;

    private synchronized long getNextKey() {
        lastKey = nextKey;
        nextKey++;
        return lastKey;
    }

    synchronized long getLastKey() {
        return lastKey;
    }

    SetRunnable(IMap<Long, String> map,
                int mapValueSize,
                long firstKey) {
        super(map, "setAsync", true);
        this.value = generateRandomString(mapValueSize);
        this.nextKey = firstKey;
        this.lastKey = this.nextKey;
    }

    void invokeMethod() {
        map.set(getNextKey(), value);
    }
}
