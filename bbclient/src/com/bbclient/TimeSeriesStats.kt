package com.bbclient

import com.bbclient.com.bbclient.RingBuffer
import com.bbclient.com.bbclient.TimeSeriesQueue
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.update
import kotlin.math.sqrt
import kotlin.time.Duration
import kotlin.time.Duration.Companion.milliseconds
import kotlin.time.Duration.Companion.seconds
import kotlin.time.TimeSource
import kotlin.time.measureTime

class TimeSeriesStats(windowSizeMillis: Long): CoroutineScope by MainScope() {
    private val numBuckets = 20
    private val windowSize = windowSizeMillis.milliseconds
    private val bucketDuration = windowSize.div(numBuckets)
    private val statsBuckets = RingBuffer<TimeSeriesQueue>(numBuckets + 1)
    private var newestBucket: TimeSeriesQueue
    private val timeSource = TimeSource.Monotonic
    private val backgroundJob: Job
    private val updatePeriod = windowSize // default

    init {
        newestBucket = statsBuckets.enqueue(TimeSeriesQueue(bucketDuration))
        backgroundJob = startAutoUpdate()
    }

    private fun addNewBucket(): TimeSeriesQueue {
        return statsBuckets.enqueue(TimeSeriesQueue(bucketDuration))
    }

    /*
     * Statistics Data Class
     */
    data class StatsGroup(
        val n: Long,
        val meanValue: Double,
        val stddev: Double,
        val minValue: Double,
        val maxValue: Double,
        val timeToCompute: Duration)

    private val statsGroup= MutableStateFlow(StatsGroup(0L,0.0,0.0,0.0,0.0, 0.seconds))

    private fun updateStats() {
        var n: Long
        var meanValue: Double
        var stddev: Double
        var minValue: Double
        var maxValue: Double

        /*
         * Trim the oldest bucket
         */
        val timeTaken = measureTime {
            val oldestTimeAllowed = timeSource.markNow() - windowSize
            val oldestBucket = statsBuckets.peekHead()
            val oldestTime = oldestBucket.trimOlderThan(oldestTimeAllowed) // CPU intensive, potentially
            assert(oldestTime >= oldestTimeAllowed)

            /*
             * Now we have exactly the window size, so calculate the statistics
             */
            n = statsBuckets.sumOf { it.count }
            meanValue = (statsBuckets.sumOf { it.total }) / n
            stddev = sqrt(statsBuckets.sumOf { it.getSumOfSquaredVariances(meanValue) } / n)
            minValue = statsBuckets.minOf { it.minValue }
            maxValue = statsBuckets.maxOf { it.maxValue }
        }

        statsGroup.update { StatsGroup(n, meanValue, stddev, minValue, maxValue, timeTaken) }
    }

    fun startAutoUpdate() = launch(Dispatchers.Default) {
        while (true) {
            delay(updatePeriod)
            launch { updateStats() }
        }
    }

    /*
     * Public functions
     */
    fun add(value: Double) {
        while (true) {
            // See if this value fits within the timespan of the newest bucket
            val inserted = newestBucket.add(value)

            if (inserted) break

            // It didn't fit within the timespan, so we need to add a new bucket
            newestBucket = addNewBucket()
        }
    }

    private fun getStats(): StatsGroup {
        return statsGroup.value
    }

    val n get() = getStats().n
    val meanValue get() = getStats().meanValue
    val stddev get() = getStats().stddev
    val minValue get() = getStats().minValue
    val maxValue get() = getStats().maxValue

    fun isWindowFull(): Boolean = statsBuckets.ringSize >= numBuckets

    fun windowFullPercentage() = statsBuckets.ringSize.toDouble() / numBuckets.toDouble()

    override fun toString(): String {
        return getStats().toString()
    }

    fun toCSV(): String {
        val sg = getStats()
        return listOf(
            sg.n,
            sg.meanValue,
            sg.stddev,
            sg.minValue,
            sg.maxValue
        ).joinToString(separator=",")
    }
}
