package com.bbclient

import kotlinx.coroutines.*
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlin.math.min
import kotlin.math.sqrt
import kotlin.time.Duration
import kotlin.time.Duration.Companion.milliseconds
import kotlin.time.Duration.Companion.seconds
import kotlin.time.TimeSource
import kotlin.time.measureTime

typealias TimeMark = TimeSource.Monotonic.ValueTimeMark

fun millisToString(runtimeMillis: Double): String = "%,.2fms".format(runtimeMillis)

class TimeSeriesStats(windowSizeMillis: Long, private val updateSlowStats: Boolean = false): AutoCloseable {
    private val numBuckets = 10
    private val targetWindowSize = windowSizeMillis.milliseconds
    private val bucketDuration = targetWindowSize.div(numBuckets)
    private val coroutineScope = CoroutineScope(Dispatchers.Default)
    private val timeSource = TimeSource.Monotonic
    /* Channel for new insertions */
    private val submitChannelBuffer = 64
    private val submitChannel = Channel<Double>(submitChannelBuffer)

    var hasUpdatedAfterWindowFilled = false
        private set

    data class TimeSeriesData(val timestamp: TimeMark, val value: Double)

    private val jobs = object {
        private var autoUpdateJob = if (updateSlowStats) { launchAutoUpdater() } else null
        private val metricsReporterJob = launchMetricsReporter()
        private val submitConsumerJob = launchSubmitConsumer()

        fun close() {
            runBlocking {
                submitConsumerJob.cancelAndJoin()
                metricsReporterJob.cancelAndJoin()
                autoUpdateJob?.cancelAndJoin()
                submitChannel.close()
            }
        }
    }

    /* Protected by a mutex */
    private val statsRingBufferMutex = Mutex()
    private val statsRingBuffer = RingBuffer(
        capacity = numBuckets + 1,
        dequeueCallback = {
                removed: TimeSeriesQueue ->
            coroutineScope.launch {
                assert(statsRingBufferMutex.isLocked)
                statsFlow.update {
                    it.copy(
                        n = it.n - removed.getCount(),
                        total = it.total - removed.getTotal(),
                        mean = it.total / it.n,
                        windowSize = it.windowSize - bucketDuration
                    )
                }
            }
        }
    )

    /*
     * Data class that collects all statistics together. These are protected by a MutableStateFlow
     */
    data class StatsGroup(
        var n: Int,
        var total: Double,
        var mean: Double,
        var windowSize: Duration,
        val stddev: Double,
        val minValue: Double,
        val maxValue: Double
    )
    private val statsFlow = MutableStateFlow(
        StatsGroup(
            n = 0,
            total = 0.0,
            mean = 0.0,
            windowSize = 0.seconds,
            stddev = 0.0,
            minValue = 0.0,
            maxValue = 0.0
        )
    )
    val stddev get() = statsFlow.value.stddev
    val mean get() = statsFlow.value.mean

    /*
     * "Slow" statistics. All of the following protected by MutableStateFlow
     */

    /* How often to update the slow statistics */
    private val updatePeriod = targetWindowSize // default

    suspend fun submit(value: Double) {
        insertSubmitTime(
            measureTime {
                submitChannel.send(value)
            }.inWholeMicroseconds.toDouble()
        )
    }

    fun submitBlocking(value: Double) {
        runBlocking {
            submit(value)
        }
    }

    private fun launchSubmitConsumer() = coroutineScope.launch{
        while (true) {
            val nextValue = submitChannel.receive()
            insertAddTime(
                measureTime {
                    add(TimeSeriesData(timestamp = timeSource.markNow(), value = nextValue))
                }.inWholeMicroseconds.toDouble()
            )
        }
    }

    private fun launchAutoUpdater() = coroutineScope.launch {
        while (true) {
            delay(updatePeriod)
            insertUpdateTime(
                measureTime {
                    updateStats()
                }.inWholeMilliseconds.toDouble()
            )
        }
    }

    private fun launchMetricsReporter() = coroutineScope.launch {
        while (true) {
            delay(4000)
            report()
        }
    }
    /*
     * Internal metrics collection and reporting, to check performance.
     */
    companion object {
        private const val BUFFERSIZE = 64
        private val addTimes = RingBuffer<Double>(BUFFERSIZE)
        private val updateTimes = RingBuffer<Double>(BUFFERSIZE)
        private val submitTimes = RingBuffer<Double>(BUFFERSIZE)
        private suspend fun report() { // called occasionally
            val reportStrings = mutableListOf<String>()
            if (addTimes.isNotEmpty())
                reportStrings.add("add() processing => %.2fµs".format(addTimes.average()))
            if (updateTimes.isNotEmpty())
                reportStrings.add("update() processing => %.2fms".format(updateTimes.average()))
            if (submitTimes.isNotEmpty())
                reportStrings.add("submit() processing => %.2fµs".format(submitTimes.average()))
            if (reportStrings.isNotEmpty())
                println("Avg Proc Times: " + reportStrings.joinToString(" / "))
        }
        private suspend fun insertAddTime(value: Double) { addTimes.enqueue(value) }
        private suspend fun insertUpdateTime(value: Double) { updateTimes.enqueue(value) }
        private suspend fun insertSubmitTime(value: Double) { submitTimes.enqueue(value) }
    }

    override fun close() {
        jobs.close()
    }

    private suspend fun add(tsdatum: TimeSeriesData) {
        suspend fun addNewBucket(startTime: TimeMark) {
            // This new bucket is empty, so it doesn't yet affect our fast stats
            statsRingBuffer.enqueue(
                TimeSeriesQueue(
                    startTime = startTime,
                    endTime = startTime + bucketDuration
                )
            )
        }

        var totalWindowAdded: Duration = 0.milliseconds
        var newestBucket: TimeSeriesQueue

        statsRingBufferMutex.withLock {
            // If the ring buffer is empty, create a new bucket
            if (statsRingBuffer.isEmpty())
                addNewBucket(startTime = tsdatum.timestamp)

            // Is our new item too new for our newest bucket? If so make a new one
            newestBucket = statsRingBuffer.peekTail()
            while (true) {
                if (tsdatum.timestamp > newestBucket.endTime) {
                    totalWindowAdded += bucketDuration - newestBucket.getTailWindowSize()
                    newestBucket.setWasCounted()
                    addNewBucket(startTime = newestBucket.endTime)
                    newestBucket = statsRingBuffer.peekTail()
                } else {
                    break
                }
            }

            assert(!newestBucket.getWasCounted())

            assert(tsdatum.timestamp >= newestBucket.startTime && tsdatum.timestamp <= newestBucket.endTime)
            totalWindowAdded += newestBucket.add(tsdatum)

            statsFlow.update {
                it.copy(
                    n = it.n + 1,
                    total = it.total + tsdatum.value,
                    mean = it.total / it.n,
                    windowSize = it.windowSize + totalWindowAdded
                )
            }
        }
    }

    private suspend fun updateStats() {
        val newestTime: TimeMark
        val oldestBucket: TimeSeriesQueue
        val absoluteWindowSize: Duration

        statsRingBufferMutex.withLock {
            /*
             * See if we have any buckets at all. If we don't, then there's nothing to do.
             */
            if (statsRingBuffer.isEmpty())
                return

            /*
             * Trim the oldest bucket
             */
            newestTime = statsRingBuffer.peekTail().getTailNewestTime()
            val oldestTimeAllowed = newestTime - targetWindowSize
            oldestBucket = statsRingBuffer.peekHead()
            val (removedN, removedTotal) = oldestBucket.trimOlderThan(oldestTimeAllowed) // CPU intensive, potentially
            val oldestTime = oldestBucket.getHeadOldestTime()
            absoluteWindowSize = newestTime - oldestTime
            assert(oldestTime >= oldestTimeAllowed)
            assert(newestTime - oldestTimeAllowed == targetWindowSize)
            assert(absoluteWindowSize <= targetWindowSize)

            statsFlow.update {
                it.copy(
                    n = it.n - removedN,
                    total = it.total - removedTotal,
                    mean = it.total / it.n
                )
            }

            statsFlow.value.let { new ->
                coroutineScope {
                    assert(new.windowSize == newestTime - oldestBucket.startTime)
                    assert(new.windowSize - (bucketDuration - oldestBucket.getHeadWindowSize()) == absoluteWindowSize)
                    assert(new.n == statsRingBuffer.sumOf { x -> x.getCount() })
                    statsFlow.update {
                        it.copy(
                            stddev = sqrt(statsRingBuffer.sumOf { x -> x.getSumOfSquaredVariances(it.mean) } / it.n),
                            minValue = statsRingBuffer.minOf { x -> x.getMin() },
                            maxValue = statsRingBuffer.maxOf { x -> x.getMax() }
                        )
                    }
                }
            }
        }

        if (statsRingBuffer.getSize() >= numBuckets)
            hasUpdatedAfterWindowFilled = true
    }

    private suspend fun windowFullPercentage() = statsRingBufferMutex.withLock {
        statsRingBuffer.getSize().toDouble() / numBuckets.toDouble()
    }

    fun toStatsString(): String {
        val stringList = mutableListOf<String>()
        runBlocking {
            statsFlow.value.let {
                val windowFullPct = min(100, (windowFullPercentage() * 100.0).toInt())
                stringList.add("N=%,d".format(it.n))

                if (it.n > 0) {
                    val rate = it.n.toDouble() * 1_000.0 / it.windowSize.inWholeMilliseconds.toDouble()
                    stringList.add("RATE=%,.1f/s".format(rate))
                    stringList.add("WDW=%,dms".format(it.windowSize.inWholeMilliseconds))

                    if (!hasUpdatedAfterWindowFilled && windowFullPct < 100)
                        stringList.add("WFP=%d%%".format(windowFullPct))

                    if (hasUpdatedAfterWindowFilled) {
                        stringList.add(
                            "µ=%s σ=%s [%s⇠⇢%s]".format(
                                millisToString(it.mean),
                                millisToString(it.stddev),
                                millisToString(it.minValue),
                                millisToString(it.maxValue)
                            )
                        )
                    }
                }

            }
        }
        return stringList.joinToString(separator = " ")
    }

    fun toCSV() = runBlocking {
        statsFlow.value.let {
            listOf(
                it.n,
                it.mean,
                it.stddev,
                it.minValue,
                it.maxValue
            ).joinToString(separator=",")
        }
    }
}
