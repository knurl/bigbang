package com.bbclient

import kotlin.time.Duration
import kotlin.time.TimeSource

class Stopwatch(private val timeout: Duration) {
    private val timeSource = TimeSource.Monotonic
    private var lastTimeCheck = timeSource.markNow()

    fun isTimeOver(): Boolean {
        val timeNow = timeSource.markNow()
        if ((timeNow - lastTimeCheck) >= timeout) {
            // Stopwatch just went off! Advance the last time check immediately
            lastTimeCheck = timeNow

            return true
        }

        return false
    }
}
