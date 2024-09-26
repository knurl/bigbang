package com.bbclient

import kotlin.time.TimeSource

class Stopwatch(private val timeoutMillis: Long) {
    private val timeSource = TimeSource.Monotonic
    private var lastTimeCheck = timeSource.markNow()

    fun isTimeOver(): Boolean {
        val timeNow = timeSource.markNow()
        if ((timeNow - lastTimeCheck).inWholeMilliseconds >= timeoutMillis) {
            // Stopwatch just went off! Advance the last time check immediately
            lastTimeCheck = timeNow

            return true
        }

        return false
    }
}
