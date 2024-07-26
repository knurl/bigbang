package com.bbclient;

import com.hazelcast.map.IMap;

import java.util.Random;

import static com.bbclient.RandomStringBuilder.generateRandomString;

public class PutIfAbsentRunnable extends IMapMethodRunnable {
    Random random;
    final private int mapValueSizeMin;
    final private int mapValueSizeMax;
    final private long firstKey;
    final private long lastKey;
    private long nextKey;

    PutIfAbsentRunnable(IMap<Long, String> map,
                        int mapValueSizeMin,
                        int mapValueSizeMax,
                        long firstKey,
                        long lastKey) {
        super(map, "putIfAbsent");
        this.random = new Random();
        this.mapValueSizeMin = mapValueSizeMin;
        this.mapValueSizeMax = mapValueSizeMax;
        this.firstKey = firstKey;
        this.lastKey = lastKey;
        this.nextKey = firstKey;
    }

    String prepare() {
        int mapValueSize = random.nextInt(mapValueSizeMin, mapValueSizeMax);
        return generateRandomString(mapValueSize);
    }

    void invokeMethod(String newValue) {
        var oldValue = super.map.putIfAbsent(nextKey, newValue);
        /* We always use keys we've used before! */
        assert (oldValue != null);
        nextKey++;
        if (nextKey > lastKey)
            nextKey = firstKey;
    }
}
