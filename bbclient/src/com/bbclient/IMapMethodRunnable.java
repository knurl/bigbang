package com.bbclient;

import com.hazelcast.map.IMap;

import java.time.Duration;
import java.time.Instant;

abstract class IMapMethodRunnable implements Runnable {
    private final String methodName;
    protected final IMap<Long, String> map;
    private final boolean quiet;

    /*
     * Synchronized
     */
    private final MovingAverage ma;

    IMapMethodRunnable(IMap<Long, String> map,
                       String methodName,
                       boolean quiet) {
        this.map = map;
        this.methodName = methodName;
        this.ma = new MovingAverage(methodName);
        this.quiet = quiet;
    }

    abstract void invokeMethod();

    public void run() {
        Instant start = Instant.now(), finish;
        boolean exceptionDuringOperation = false;
        try {
            invokeMethod();
            finish = Instant.now();
        } catch (Throwable ex) {
            finish = Instant.now();
            exceptionDuringOperation = true;
            Logger.log("*** EXCEPTION [%s] *** %s".formatted(methodName,
                    ex.getClass().getSimpleName()));
        }

        var runtime = Duration.between(start, finish).toMillis();
        synchronized (this) {
            ma.add(runtime, exceptionDuringOperation, quiet);
        }
    }

    public String toString() {
        synchronized (this) {
            return "==> %s() %s".formatted(methodName, ma.toString());
        }
    }
}
