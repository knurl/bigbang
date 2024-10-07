package com.bbclient

import kotlin.math.max
import kotlin.math.min
import kotlin.math.pow
import kotlin.time.Duration

class TimeSeriesQueue(
    val startTime: TimeMark,
    val endTime: TimeMark,
    initialCapacity: Int = 128) {

    private val queue = ArrayDeque<TimeSeriesStats.TimeSeriesData>(initialCapacity)
    private var total = 0.0
    private var oldestTime: TimeMark? = null
    private var newestTime: TimeMark? = null
    private var minValue: Double? = null
    private var maxValue: Double? = null
    private var wasCounted = false

    fun getTotal() = total
    fun getCount() = queue.size
    private fun adjustOldestNewest(timestamp: TimeMark) {
        oldestTime = oldestTime?: timestamp
        oldestTime = if (oldestTime!! < timestamp) oldestTime else timestamp

        newestTime = newestTime?: timestamp
        newestTime = if (newestTime!! > timestamp) newestTime else timestamp
    }

    fun getMin() = minValue?: Double.MAX_VALUE

    fun getMax() = maxValue?: Double.MIN_VALUE

    private fun adjustMinMax(value: Double) {
        minValue = min(value, getMin())
        maxValue = max(value, getMax())
    }

    fun getTailWindowSize() = getTailNewestTime() - startTime

    private fun getTailNewestTime() = newestTime?: startTime

    fun setWasCounted() {
        wasCounted = true
    }

    fun getWasCounted() = wasCounted

    // Returns Duration added on successful add; otherwise returns null on failure
    fun add(tsdatum: TimeSeriesStats.TimeSeriesData): Duration {
        val windowAdded: Duration

        assert(!wasCounted)
        if (tsdatum.timestamp < startTime || tsdatum.timestamp > endTime)
            throw IndexOutOfBoundsException()

        val origNewestTime = getTailNewestTime()
        assert(tsdatum.timestamp >= origNewestTime)
        queue.add(tsdatum)
        total += tsdatum.value
        adjustMinMax(tsdatum.value)
        adjustOldestNewest(tsdatum.timestamp)
        windowAdded = getTailNewestTime() - origNewestTime

        return windowAdded
    }

    fun getSumOfSquaredVariances(mean: Double): Double {
        var sumSqVar = 0.0
        queue.forEach { sumSqVar += (it.value - mean).pow(2.0) }
        return sumSqVar
    }
}
