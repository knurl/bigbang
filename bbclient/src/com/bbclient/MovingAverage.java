package com.bbclient;

import org.apache.commons.math3.stat.descriptive.DescriptiveStatistics;

public class MovingAverage {
    private final String name;
    private final DescriptiveStatistics stats;
    private long failedCount = 0;
    private final int population = 1 << 14;
    final int minPopulation = population >> 2;

    public MovingAverage(String name) {
        this.name = name;
        this.stats = new DescriptiveStatistics(population);
    }

    static String toSeconds(double runtime) {
        return "%,.3fs".formatted(runtime / 1000.0f);
    }

    public void add(double value, boolean operationFailed, boolean quiet) {
        final int outlierNumStddev = 5; // * stddev from mean

        stats.addValue(value);
        if (operationFailed)
            failedCount++;

        if (quiet || stats.getN() < minPopulation)
            return;

        final var mean = stats.getMean();
        final var stddev = stats.getStandardDeviation();
        final var distanceFromMean = Math.abs(value - mean);
        final var numStdDev = (long)Math.floor(distanceFromMean / stddev);
        if (numStdDev >= outlierNumStddev) {
            Logger.log("%s(): |T-µ| >= %dσ T=%s µ=%s σ=%s".formatted(
                    name,
                    numStdDev,
                    toSeconds(value),
                    toSeconds(mean),
                    toSeconds(stddev)));
        }
    }

    public String toString() {
        final long N = stats.getN();
        if (N == 0)
            return "N=0";

        String fail = "@";
        if (failedCount > 0)
            fail = "[%,d FAIL] @".formatted(failedCount);

        if (N < minPopulation) {
            final double MP = Math.min((double) N / (double) minPopulation, 1.0);
            return "N=%,d MP=%d%% %s { MIN=%s | MAX=%s }".formatted(
                    N,
                    (int)(MP * 100.0),
                    fail,
                    toSeconds(stats.getMin()),
                    toSeconds(stats.getMax()));
        }

        return "N=%,d %s { MIN=%s | µ=%s σ=%s | MAX=%s }".formatted(
                N,
                fail,
                toSeconds(stats.getMin()),
                toSeconds(stats.getMean()),
                toSeconds(stats.getStandardDeviation()),
                toSeconds(stats.getMax()));
    }
}
