package com.bbclient;

import org.apache.commons.math3.stat.descriptive.DescriptiveStatistics;

import java.util.ArrayList;
import java.util.LinkedList;
import java.util.List;

public class MovingAverage {
    private final String name;
    private final DescriptiveStatistics stats;
    private long failedCount = 0;
    private final Logger logger;
    private final int minPopulation;

    public MovingAverage(String name) {
        int population;
        if (!Main.rapidTestMode) {
            population = 1 << 12;
        } else {
            population = 1 << 7;
        }
        this.minPopulation = population >> 2;

        this.name = name;
        this.stats = new DescriptiveStatistics(population);
        this.logger = new Logger(name);
    }

    public void clearStats() {
        stats.clear();
    }

    public boolean hasReachedMinimumPopulation() {
        return stats.getN() >= minPopulation;
    }

    static String millisToString(double runtime) {
        return "%,.2fms".formatted(runtime);
    }

    public void add(double value, boolean operationFailed, boolean quiet) {
        final int outlierNumStddev = 10; // * stddev from mean

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
        stringList.add(name + "() =>");

        final long N = stats.getN();
        stringList.add("N=%d".formatted(stats.getN()));

        if (N > 0) {
            if (failedCount > 0) {
                var numFailed = "[%d FAIL]".formatted(failedCount);
                stringList.add(numFailed);
            }

            String descStat;
            if (N >= minPopulation) {
                descStat = "µ=%s σ=%s".formatted(
                        millisToString(stats.getMean()),
                        millisToString(stats.getStandardDeviation()));
            } else {
                final double MP = Math.min((double) N / (double) minPopulation, 1.0);
                descStat = "MP=%d%%".formatted((int) (MP * 100.0));
            }
            stringList.add(descStat);

            String range = "[%s ⇠⇢ %s]".formatted(
                    millisToString(stats.getMin()),
                    millisToString(stats.getMax()));
            stringList.add(range);
        }

        return String.join(" ", stringList);
    }

    public String toCSV() {
        List<String> stringList = new ArrayList<>();
        stringList.add(name);
        stringList.add("%d".formatted(stats.getN()));
        stringList.add("%d".formatted(Math.round(stats.getMean())));
        stringList.add("%d".formatted(Math.round(stats.getStandardDeviation())));
        stringList.add("%d".formatted(Math.round(stats.getMin())));
        stringList.add("%d".formatted(Math.round(stats.getMax())));
        return String.join(",", stringList);
    }
}
