package com.bbclient

import kotlinx.coroutines.DelicateCoroutinesApi
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.newSingleThreadContext
import kotlinx.coroutines.withContext
import kotlin.coroutines.CoroutineContext
import kotlin.math.max
import kotlin.math.min
import kotlin.math.pow
import kotlin.time.Duration
import kotlin.time.Duration.Companion.milliseconds

class TimeSeriesQueue(
    val startTime: TimeMark,
    val endTime: TimeMark,
    initialCapacity: Int = 128) {

    /*
     * Synchronized through use of a single thread.
     */
    @OptIn(ExperimentalCoroutinesApi::class, DelicateCoroutinesApi::class)
    private val confined: CoroutineContext = newSingleThreadContext("DequeueContext")
    private val queue = ArrayDeque<TimeSeriesStats.TimeSeriesData>(initialCapacity)
    private var total = 0.0
    private var oldestTime: TimeMark? = null
    private var newestTime: TimeMark? = null
    private var minValue: Double? = null
    private var maxValue: Double? = null
    private var wasCounted = false

    suspend fun getTotal() = withContext(confined) { total }
    suspend fun getCount() = withContext(confined) { queue.size }
    private suspend fun adjustOldestNewest(timestamp: TimeMark) = withContext(confined) {
        oldestTime = oldestTime?: timestamp
        oldestTime = if (oldestTime!! < timestamp) oldestTime else timestamp

        newestTime = newestTime?: timestamp
        newestTime = if (newestTime!! > timestamp) newestTime else timestamp
    }
    suspend fun getMin() = withContext(confined) {
        minValue?: Double.MAX_VALUE
    }
    suspend fun getMax() = withContext(confined) {
        maxValue?: Double.MIN_VALUE
    }
    private suspend fun adjustMinMax(value: Double) = withContext(confined) {
        minValue = min(value, getMin())
        maxValue = max(value, getMax())
    }
    suspend fun getTailWindowSize() = withContext(confined) {
        getTailNewestTime() - startTime
    }
    suspend fun getTailNewestTime() = withContext(confined) {
        newestTime?: startTime
    }
    suspend fun getHeadWindowSize() = withContext(confined) {
        endTime - getHeadOldestTime()
    }
    suspend fun getHeadOldestTime() = withContext(confined) {
        oldestTime?: endTime
    }
    suspend fun setWasCounted() = withContext(confined) {
        wasCounted = true
    }
    suspend fun getWasCounted() = withContext(confined) {
        wasCounted
    }

    // Returns Duration added on successful add; otherwise returns null on failure
    suspend fun add(tsdatum: TimeSeriesStats.TimeSeriesData): Duration {
        var windowAdded: Duration

        withContext(confined) {
            assert(!wasCounted)
            if (tsdatum.timestamp < startTime || tsdatum.timestamp > endTime)
                throw IndexOutOfBoundsException()

            val origNewestTime = getTailNewestTime()
            queue.add(tsdatum)
            total += tsdatum.value
            adjustMinMax(tsdatum.value)
            adjustOldestNewest(tsdatum.timestamp)
            windowAdded = getTailNewestTime() - origNewestTime
        }

        return windowAdded
    }

    suspend fun trimOlderThan(oldestTimeAllowed: TimeMark): TimeSeriesStats.FastStatsGroup {
        var numRemoved = 0
        var totalValueRemoved = 0.0
        var windowSizeRemoved = 0.milliseconds
        var oldestTimeReturned: TimeMark

        withContext(confined) {
            val origSize = queue.size
            val origTotal = total
            val origHeadWindowSize = getHeadWindowSize()
            var oldestSurvivorFound = false

            while (queue.size > 0) {
                val oldestItem = queue.first()
                oldestTime = oldestItem.timestamp

                // We found an item in the queue that is new enough to survive.
                if (oldestTime!! >= oldestTimeAllowed) {
                    oldestSurvivorFound = true
                    break
                }

                // The oldItem isn't new enough to survive, so remove it
                val toRemove = queue.removeFirst()
                assert(toRemove == oldestItem)
                total -= toRemove.value
            }

            if (oldestSurvivorFound) {
                assert(queue.size > 0)
                assert(oldestTime!! == queue.first().timestamp)
                assert(oldestTime!! >= oldestTimeAllowed)
                minValue = queue.minOf { it.value }
                maxValue = queue.maxOf { it.value }
            } else {
                assert(queue.size == 0)
                total = 0.0
                oldestTime = null
                newestTime = null
            }

            assert(origSize >= queue.size)
            numRemoved = origSize - queue.size

            totalValueRemoved = origTotal - total

            windowSizeRemoved = getHeadWindowSize() - origHeadWindowSize
            oldestTimeReturned = getHeadOldestTime()
            assert(oldestTimeReturned >= oldestTimeAllowed)
        }

        return TimeSeriesStats.FastStatsGroup(numRemoved, totalValueRemoved, 0.0, windowSizeRemoved)
    }

    suspend fun getSumOfSquaredVariances(mean: Double): Double {
        var sumSqVar = 0.0
        withContext(confined) {
            queue.forEach { sumSqVar += (it.value - mean).pow(2.0) }
        }
        return sumSqVar
    }
}
