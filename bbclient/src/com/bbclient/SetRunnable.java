package com.bbclient;

import com.hazelcast.map.IMap;

import static com.bbclient.RandomStringBuilder.generateRandomString;

class SetRunnable extends IMapMethodRunnable {
    private final String value;

    /*
     * synchronized
     */
    private int nextKey;
    private int lastKey;

    private synchronized int getNextKey() {
        lastKey = nextKey;
        nextKey++;
        return lastKey;
    }

    synchronized int getLastKey() {
        return lastKey;
    }

    SetRunnable(IMap<Integer, String> map,
                int mapValueSize,
                int firstKey) {
        super(map, "setAsync", true);
        this.value = generateRandomString(mapValueSize);
        this.nextKey = firstKey;
        this.lastKey = this.nextKey;
    }

    void invokeMethod() {
        map.set(getNextKey(), value);
    }
}
