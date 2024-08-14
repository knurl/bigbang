package com.bbclient;

import java.time.Duration;
import java.time.Instant;
import java.util.concurrent.ArrayBlockingQueue;

class Stopwatch {
    private final long timeout; // milliseconds
    private Instant lastTimeCheck;

    // Sliding-window for calculating transfer rates against our Stopwatch
    final int slidingWindowLength = 3;
    final private ArrayBlockingQueue<Long> countsQueue;
    long currentCount = 0;
    long totalCount = 0;

    double currentRate = 0.0;

    Stopwatch(long timeout) {
        this.timeout = timeout;
        lastTimeCheck = Instant.now();
        countsQueue = new ArrayBlockingQueue<>(slidingWindowLength);
    }

    boolean isTimeOver() {
        final var timeNow = Instant.now();
        var timeElapsed = Duration.between(lastTimeCheck, timeNow).toMillis();
        if (timeElapsed < timeout)
            return false;

        // Stopwatch just went off! Move the last time check forward immediately
        lastTimeCheck = timeNow;

        if (countsQueue.remainingCapacity() < 1) {
            var removedCount = countsQueue.poll(); // avoid blocking behavior
            assert (removedCount != null);
            totalCount -= removedCount;
        }

        // Shouldn't block
        countsQueue.add(currentCount);
        totalCount += currentCount;

        // Now reset the current count for the next round
        currentCount = 0;

        // Calculate the sliding-window average rate
        currentRate = (double) totalCount * 1000.0 / (countsQueue.size() * timeout);
        return true;
    }

    void addUnit() {
        currentCount++;
    }

    double ratePerSecond() {
        return currentRate;
    }
}
