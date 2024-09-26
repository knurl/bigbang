package com.bbclient;

import com.hazelcast.map.IMap;
import org.jetbrains.annotations.Contract;
import org.jetbrains.annotations.NotNull;

import java.time.Duration;
import java.time.Instant;

abstract class IMapMethodRunnable implements Runnable, AutoCloseable {
    private final String methodName;
    protected final IMap<Integer, String> map;
    private final boolean quiet;
    private final Logger logger;
    private int numFailed = 0;
    private final long windowSizeMillis;
    private TimeSeriesStats stats;

    IMapMethodRunnable(IMap<Integer, String> map,
                       String methodName,
                       boolean quiet) {
        this.methodName = methodName;
        this.map = map;
        this.quiet = quiet;
        this.logger = new Logger(methodName);

        if (!Main.localTestMode) {
            this.windowSizeMillis = 60_000;
        } else {
            this.windowSizeMillis = 3_000;
        }

        this.stats = new TimeSeriesStats(this.windowSizeMillis, !quiet);
    }

    public void close() {
        stats.close();
    }

    private void add(double value) {
        stats.submitBlocking(value);

        if (!quiet && stats.getHasUpdatedAfterWindowFilled()) {
            final var stddev = stats.getStddev();
            final int outlierNumStddev = 10; // * stddev from mean
            final int maxStddev = 20;
            final var mean = stats.getMeanBlocking();
            int numStdDev;

            if (stddev == 0.0)
                numStdDev = Integer.MAX_VALUE;
            else
                numStdDev = (int)Math.floor(Math.abs(value - mean) / stddev);

            if (outlierNumStddev * stddev <= numStdDev && numStdDev < maxStddev)
                logger.log("%s: |T-µ| >= %dσ T=%s µ=%s σ=%s".formatted(
                        this,
                        numStdDev,
                        millisToString(value),
                        millisToString(mean),
                        millisToString(stddev)));
        }
    }

    /*
     * TODO: Technically the following two functions change shared mutable state,
     *       but in the first case the value is monotonically increasing, and in the
     *       second it's a pointer swap, so we should be Ok for both.
     */
    public boolean hasReachedMinimumPopulation() {
        return stats.getHasUpdatedAfterWindowFilled();
    }

    public void clearStats() {
        stats.close();
        stats = new TimeSeriesStats(this.windowSizeMillis, !this.quiet);
    }

    public String toString() {
        return methodName + "()";
    }

    @Contract(pure = true)
    private @NotNull String millisToString(double runtimeMillis) {
        return "%,.2fms".formatted(runtimeMillis);
    }

    public synchronized String toStatsString() {
        String failedString = "";
        if (numFailed > 0)
            failedString = "[%d FAILED]".formatted( numFailed);
        return "%s->{%s}%s".formatted( this, stats.toStatsString(), failedString);
    }

    public synchronized String toCSV() {
        return stats.toCSV();
    }

    abstract void invokeMethod();

    public void run() {
        Instant start = Instant.now(), finish;
        try {
            invokeMethod();
            finish = Instant.now();
        } catch (Throwable ex) {
            finish = Instant.now();
            numFailed++;
            logger.log("*** EXCEPTION [%s] *** %s".formatted(methodName,
                    ex.getClass().getSimpleName()));
        }

        var runtime = Duration.between(start, finish).toMillis();
        add(runtime);
    }
}
