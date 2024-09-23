package com.bbclient.com.bbclient

import java.util.*
import kotlin.math.round
import kotlin.time.TimeSource

open class Stopwatch @JvmOverloads constructor(private val timeoutMillis: Int,
                                               measurementPeriodMillis: Int = timeoutMillis) {
    private val timeSource = TimeSource.Monotonic
    private var lastTimeCheck = timeSource.markNow()
    private val slidingWindowLength = round((measurementPeriodMillis.toDouble() / timeoutMillis)).toInt()
    private val countsQueue: Queue<Int> = LinkedList()
    private var currentCount = 0
    private var totalCount = 0
    private var currentRate = 0.0

    fun isTimeOver(): Boolean {
        val timeNow = timeSource.markNow()
        if ((timeNow - lastTimeCheck).inWholeMilliseconds >= timeoutMillis) {
            // Stopwatch just went off! Advance the last time check immediately
            lastTimeCheck = timeNow

            // If our queue is too big, remove one element and subtract that element from the total count
            if (countsQueue.size >= slidingWindowLength) {
                val removedCount = countsQueue.remove()
                totalCount -= removedCount
            }

            // Now add the current count to the queue
            countsQueue.add(currentCount)
            totalCount += currentCount

            // Now reset the current count for the next round
            currentCount = 0

            // Calculate the sliding-window average rate
            currentRate = (totalCount * 1000.0) / (countsQueue.size * timeoutMillis)
            return true
        }

        return false
    }

    fun addUnit() {
        currentCount++
    }

    fun ratePerSecond(): Double {
        return currentRate
    }
}
