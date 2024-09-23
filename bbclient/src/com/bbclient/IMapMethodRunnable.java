package com.bbclient;

import com.hazelcast.map.IMap;

import java.time.Duration;
import java.time.Instant;

abstract class IMapMethodRunnable implements Runnable {
    private final String methodName;
    protected final IMap<Integer, String> map;
    private final boolean quiet;
    private final Logger logger;

    /*
     * Synchronized
     */
    private final MovingAverage ma;

    private synchronized void add(double value, boolean operationFailed, boolean quiet) {
        ma.add(value, operationFailed, quiet);
    }

    public synchronized boolean hasReachedMinimumPopulation() {
        return ma.isWindowFull();
    }

    public synchronized void clearStats() {
        ma.clearStats();
    }

    public synchronized String toString() {
        return methodName + "()";
    }

    public synchronized String toStatsString() {
        return "%s->{%s}".formatted(this, ma);
    }

    public synchronized String toCSV() {
        return ma.toCSV();
    }

    /*
     * Constructor and non-synchronized methods
     */
    IMapMethodRunnable(IMap<Integer, String> map,
                       String methodName,
                       boolean quiet) {
        this.map = map;
        this.methodName = methodName;
        this.ma = new MovingAverage(methodName);
        this.quiet = quiet;
        this.logger = new Logger(methodName + "Runnable");
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
            logger.log("*** EXCEPTION [%s] *** %s".formatted(methodName,
                    ex.getClass().getSimpleName()));
        }

        var runtime = Duration.between(start, finish).toMillis();
        add(runtime, exceptionDuringOperation, quiet);
    }
}
