package com.bbclient;

import java.time.Duration;
import java.time.Instant;

class Stopwatch {
    private final long timeout; // milliseconds
    private Instant lastTimeCheck;

    Stopwatch(long timeout) {
        this.timeout = timeout;
        this.lastTimeCheck = Instant.now();
    }

    boolean isTimeOver() {
        var over = false;
        final var timeNow = Instant.now();
        final var elapsedMillis = Duration.between(lastTimeCheck, timeNow).toMillis();
        if (elapsedMillis >= timeout) {
            over = true;
            lastTimeCheck = timeNow;
        }
        return over;
    }
}
