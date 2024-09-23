package com.bbclient.com.bbclient

import kotlin.math.max
import kotlin.math.min
import kotlin.math.pow
import kotlin.time.Duration
import kotlin.time.TimeSource

class TimeSeriesQueue(windowSize: Duration, initialCapacity: Int = 128) {
    private val timeSource = TimeSource.Monotonic
    data class TimeSeriesData(val timestamp: TimeSource.Monotonic.ValueTimeMark, val value: Double)
    private val queue = ArrayDeque<TimeSeriesData>(initialCapacity)
    private val startTime = timeSource.markNow()
    private val endTime = startTime + windowSize
    private var oldestTime = startTime
    private var newestTime = startTime
    var total: Double = 0.0
    var count: Long = 0
    var minValue = Double.MAX_VALUE
    var maxValue = Double.MIN_VALUE

    // Returns true if item was inserted
    fun add(value: Double): Boolean {
        var inserted = false
        val timeNow = timeSource.markNow()
        if (timeNow >= startTime && timeNow < endTime) {
            queue.add(TimeSeriesData(timeNow, value))
            newestTime = timeNow
            if (oldestTime == startTime)
                oldestTime = timeNow
            total += value
            count += 1
            minValue = min(minValue, value)
            maxValue = max(maxValue, value)
            inserted = true
        }
        return inserted
    }

    fun getSumOfSquaredVariances(mean: Double): Double {
        var sumSqVar = 0.0
        queue.forEach { sumSqVar += (it.value - mean).pow(2.0) }
        return sumSqVar
    }

    fun trimOlderThan(oldestTimeAllowed: TimeSource.Monotonic.ValueTimeMark): TimeSource.Monotonic.ValueTimeMark {
        val oldCount = count
        assert(startTime < newestTime)
        assert(newestTime < endTime)

        while (queue.size > 0) {
            val oldestItem = queue.first()
            oldestTime = oldestItem.timestamp
            if (oldestTime >= oldestTimeAllowed)
                break
            total -= oldestItem.value
            count -= 1
            queue.removeFirst()
        }

        val numRemoved = oldCount - count
        return oldestTime
    }
}
