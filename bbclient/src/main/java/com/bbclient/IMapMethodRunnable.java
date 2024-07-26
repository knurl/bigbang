package com.bbclient;

import com.hazelcast.map.IMap;

import java.time.Duration;
import java.time.Instant;

public abstract class IMapMethodRunnable implements Runnable {
    private final String methodName;
    protected IMap<Long, String> map;
    private final MovingAverage ma;

    IMapMethodRunnable(IMap<Long, String> map,
                       String methodName) {
        this.map = map;
        this.methodName = methodName;
        this.ma = new MovingAverage(methodName);
    }

    abstract void invokeMethod(String newValue);

    String prepare() {
        return null;
    }

    public void run() {
        var prepareString = prepare();
        Instant start = Instant.now(), finish;
        boolean exceptionDuringOperation = false;
        try {
            invokeMethod(prepareString);
            finish = Instant.now();
        } catch (Throwable ex) {
            finish = Instant.now();
            exceptionDuringOperation = true;
            Main.log("*** EXCEPTION [%s] *** %s".formatted(methodName, ex.getClass().getSimpleName()));
        }

        var runtime = Duration.between(start, finish).toMillis();
        ma.add(runtime, exceptionDuringOperation);
    }

    public String toString() {
        return "==> %s() %s".formatted(methodName, ma.toString());
    }
}
