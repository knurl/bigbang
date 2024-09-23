package com.bbclient;

import java.util.LinkedList;

public class MovingAverage {
    private final String name;
    private final Logger logger;
    private final long windowSizeMillis;
    private TimeSeriesStats stats;
    private long failedCount = 0;

    public MovingAverage(String name) {
        this.name = name;
        this.logger = new Logger(name);

        if (!Main.localTestMode) {
            this.windowSizeMillis = 60_000;
        } else {
            this.windowSizeMillis = 2_000;
        }

        this.stats = new TimeSeriesStats(windowSizeMillis);
    }

    public void clearStats() {
        stats = new TimeSeriesStats(windowSizeMillis);
    }

    public boolean isWindowFull() {
        return stats.isWindowFull();
    }

    static String millisToString(double runtime) {
        return "%,.2f".formatted(runtime);
    }

    public void add(double value, boolean operationFailed, boolean quiet) {
        final int outlierNumStddev = 10; // * stddev from mean

        stats.add(value);
        if (operationFailed)
            failedCount++;

        if (quiet || !isWindowFull())
            return;

        final var mean = stats.getMeanValue();
        final var stddev = stats.getStddev();
        final var distanceFromMean = Math.abs(value - mean);
        final var numStdDev = (long)Math.floor(distanceFromMean / stddev);
        if (numStdDev >= outlierNumStddev) {
            logger.log("%s(): |T-µ| >= %dσ T=%s µ=%s σ=%s".formatted(
                    name,
                    numStdDev,
                    millisToString(value),
                    millisToString(mean),
                    millisToString(stddev)));
        }
    }

    public String toString() {
        var stringList = new LinkedList<String>();

        final long N = stats.getN();
        stringList.add("N=%,d".formatted(stats.getN()));

        if (N > 0) {
            if (failedCount > 0) {
                var numFailed = "[%d FAIL]".formatted(failedCount);
                stringList.add(numFailed);
            }

            if (!isWindowFull()) {
                final double MP = stats.windowFullPercentage() * 100.0;
                stringList.add("MP=%d%%".formatted((int)MP));
            }

            stringList.add("µ=%s σ=%s".formatted(millisToString(stats.getMeanValue()),
                    millisToString(stats.getStddev())));

            String range = "[%s⇠⇢%s]".formatted(
                    millisToString(stats.getMinValue()),
                    millisToString(stats.getMaxValue()));
            stringList.add(range);
        }

        return String.join(" ", stringList);
    }

    public String toCSV() {
        return stats.toCSV();
    }
}
