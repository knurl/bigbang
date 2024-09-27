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
                fastStatsMutex.withLock {
                    fastStats.apply {
                        this.n -= removed.getCount()
                        this.total -= removed.getTotal()
                        this.mean = this.total / this.n
                        this.windowSize -= bucketDuration
                        assert(this.windowSize < targetWindowSize)
                    }
                }
            }
        }
    )

    /*
     * "Fast" statistics. These are protected by a Mutex.
     */
    private val fastStatsMutex = Mutex()

    data class FastStatsGroup(
        var n: Int,
        var total: Double,
        var mean: Double,
        var windowSize: Duration
    )

    private val fastStats = FastStatsGroup(0, 0.0, 0.0, 0.milliseconds)
    fun getMeanBlocking() = runBlocking {
        fastStatsMutex.withLock {
            fastStats.mean
        }
    }

    private suspend fun getFastStats() = fastStatsMutex.withLock {
        fastStats.copy()
    }

    /*
     * "Slow" statistics. All of the following protected by MutableStateFlow
     */

    /* How often to update the slow statistics */
    private val updatePeriod = targetWindowSize // default

    data class SlowStatsGroup(
        val stddev: Double,
        val minValue: Double,
        val maxValue: Double
    )

    private val slowStats = MutableStateFlow(SlowStatsGroup(0.0, 0.0, 0.0))

    private fun getSlowStats(): SlowStatsGroup {
        return slowStats.value // protected by MutableStateFlow
    }

    fun getStddev() = getSlowStats().stddev

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
        }

        fastStatsMutex.withLock {
            fastStats.apply {
                this.n += 1
                this.total += tsdatum.value
                this.mean = this.total / this.n
                this.windowSize += totalWindowAdded
            }
        }
    }

    private suspend fun updateStats() {
        val n: Int
        val meanValue: Double
        val removed: FastStatsGroup
        val newestTime: TimeMark
        val oldestBucket: TimeSeriesQueue
        val absoluteWindowSize: Duration
        val stddev: Double
        val minValue: Double
        val maxValue: Double

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
            removed = oldestBucket.trimOlderThan(oldestTimeAllowed) // CPU intensive, potentially
            val oldestTime = oldestBucket.getHeadOldestTime()
            absoluteWindowSize = newestTime - oldestTime
            assert(oldestTime >= oldestTimeAllowed)
            assert(newestTime - oldestTimeAllowed == targetWindowSize)
            assert(absoluteWindowSize <= targetWindowSize)

            fastStatsMutex.withLock {
                fastStats.apply {
                    this.n -= removed.n
                    this.total -= removed.total
                    this.mean = this.total / this.n

                    /* Don't update window size here; we remove ENTIRE buckets from the head end
                  * of the ring buffer, not PARTS of buckets. DO check that the window size
                  * matches our calculated "coarse" window size that counts whole buckets
                  * after the head bucket. */
                    assert(this.windowSize == newestTime - oldestBucket.startTime)
                    assert(this.windowSize - (bucketDuration - oldestBucket.getHeadWindowSize()) == absoluteWindowSize)
                }

                n = fastStats.n
                meanValue = fastStats.mean
            }

            /*
             * Now we have exactly the window size, so calculate the statistics. Do fast stats 1st.
             */
            assert(n == statsRingBuffer.sumOf { it.getCount() })
            stddev = sqrt(statsRingBuffer.sumOf { it.getSumOfSquaredVariances(meanValue) } / n)
            minValue = statsRingBuffer.minOf { it.getMin() }
            maxValue = statsRingBuffer.maxOf { it.getMax() }
        }

        if (statsRingBuffer.getSize() >= numBuckets)
            hasUpdatedAfterWindowFilled = true

        /*
         * Update MutableStateFlow which protects our statsGroup
         */
        slowStats.update { SlowStatsGroup(stddev, minValue, maxValue) }
    }

    private suspend fun windowFullPercentage() = statsRingBufferMutex.withLock {
        statsRingBuffer.getSize().toDouble() / numBuckets.toDouble()
    }

    fun toStatsString(): String {
        val fastStatsCopy: FastStatsGroup
        val windowFullPct: Int
        runBlocking {
            fastStatsCopy = getFastStats()
            windowFullPct = min(100, (windowFullPercentage() * 100.0).toInt())
        }

        val slowStatsCopy = getSlowStats()

        val stringList = mutableListOf("N=%,d".format(fastStatsCopy.n))

        if (fastStatsCopy.n > 0) {
            val window = fastStatsCopy.windowSize.inWholeMilliseconds.toDouble()
            val rate = fastStatsCopy.n.toDouble() * 1_000.0 / window
            stringList.add("RATE=%,.1f/s".format(rate))
            stringList.add("WDW=%,.1fs".format(window / 1_000.0))

            if (!hasUpdatedAfterWindowFilled && windowFullPct < 100)
                stringList.add("WFP=%d%%".format(windowFullPct))

            if (hasUpdatedAfterWindowFilled) {
                stringList.add(
                    "µ=%s σ=%s [%s⇠⇢%s]".format(
                        millisToString(fastStats.mean),
                        millisToString(slowStatsCopy.stddev),
                        millisToString(slowStatsCopy.minValue),
                        millisToString(slowStatsCopy.maxValue)
                    )
                )
            }
        }

        return stringList.joinToString(separator = " ")
    }

    fun toCSV() = runBlocking {
        val slowStatsCopy = getSlowStats() // protected by MutableStateFlow
        val n: Int
        val mean: Double
        fastStatsMutex.withLock {
            n = fastStats.n
            mean = fastStats.mean
        }
        listOf(
            n,
            mean,
            slowStatsCopy.stddev,
            slowStatsCopy.minValue,
            slowStatsCopy.maxValue
        ).joinToString(separator=",")
    }
}
