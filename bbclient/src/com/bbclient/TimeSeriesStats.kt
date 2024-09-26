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

class TimeSeriesStats(windowSizeMillis: Long, updateSlowStats: Boolean = false) {
    private val numBuckets = 20
    private val targetWindowSize = windowSizeMillis.milliseconds
    private val bucketDuration = targetWindowSize.div(numBuckets)
    private var autoUpdateJob: Job? = null
    private val submitConsumerJob: Job
    private val coroutineScope = CoroutineScope(Dispatchers.Default)
    var hasUpdatedAfterWindowFilled = false
        private set
    private val timeSource = TimeSource.Monotonic

    companion object {
        private var numInserts = 0
        private val addTimes = ArrayDeque<Double>()
        private val updateTimes = ArrayDeque<Double>()
        private fun report() {
            if (numInserts++ % 1000 == 0) {
                val reportStrings = mutableListOf<String>()
                if (addTimes.isNotEmpty())
                    reportStrings.add("add() processing => %.2fµs".format(addTimes.average()))
                if (updateTimes.isNotEmpty())
                    reportStrings.add("update() processing => %.2fms".format(updateTimes.average() / 1000.0))
                if (reportStrings.isNotEmpty())
                    println("Avg Proc Times: " + reportStrings.joinToString(" / "))
            }
        }
        private fun insertAddTime(value: Double) { addTimes.add(value); report() }
        private fun insertUpdateTime(value: Double) { updateTimes.add(value); report() }
    }

    data class TimeSeriesData(val timestamp: TimeMark, val value: Double)

    /* Channel for new insertions */
    private val submitChannelBuffer = 512
    private val submitChannel = Channel<Double>(submitChannelBuffer)

    /* Protected by a mutex */
    private val statsRingBufferMutex = Mutex()
    private val statsRingBuffer = RingBuffer<TimeSeriesQueue>(numBuckets + 1)

    init {
        submitConsumerJob = coroutineScope.launch {
            consumeSubmissions()
        }

        if (updateSlowStats)
            this.autoUpdateJob = startAutoUpdate()
    }

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
        submitChannel.send(value)
    }

    fun submitBlocking(value: Double) {
        runBlocking {
            submit(value)
        }
    }

    private suspend fun consumeSubmissions() {
        while (true) {
            val nextValue = submitChannel.receive()
            insertAddTime(
                measureTime {
                    add(TimeSeriesData(timestamp = timeSource.markNow(), value = nextValue))
                }.inWholeMicroseconds.toDouble()
            )
        }
    }

    private fun startAutoUpdate() = coroutineScope.launch {
        while (true) {
            delay(updatePeriod)
            insertUpdateTime(
                measureTime {
                    updateStats()
                }.inWholeMicroseconds.toDouble()
            )
        }
    }

    fun close() {
        runBlocking {
            autoUpdateJob?.cancelAndJoin()
            submitConsumerJob.cancelAndJoin()
            submitChannel.close()
        }
    }

    private suspend fun add(tsdatum: TimeSeriesData) {
        // MUST be called with ring buffer mutex held!
        suspend fun addNewBucket(startTime: TimeMark) {
            assert(statsRingBufferMutex.isLocked)

            if (!statsRingBuffer.hasCapacity()) {
                val removedBucket = statsRingBuffer.dequeue()

                fastStatsMutex.withLock {
                    fastStats.apply {
                        this.n -= removedBucket.getCount()
                        this.total -= removedBucket.getTotal()
                        this.mean = this.total / this.n
                        this.windowSize -= bucketDuration
                        assert(this.windowSize < targetWindowSize)
                    }
                }
            }
            // This new bucket is empty, so it doesn't yet affect our fast stats
            statsRingBuffer.enqueue(TimeSeriesQueue(startTime, startTime + bucketDuration))
        }

        var totalWindowAdded: Duration = 0.milliseconds

        statsRingBufferMutex.withLock {
            // If the ring buffer is empty, create a new bucket
            if (statsRingBuffer.isEmpty())
                addNewBucket(tsdatum.timestamp) // bucket start == timestamp of new datum

            // Is our new item too new for our newest bucket? If so make a new one
            var newestBucket: TimeSeriesQueue = statsRingBuffer.peekTail()
            while (true) {
                if (tsdatum.timestamp > newestBucket.endTime) {
                    totalWindowAdded += bucketDuration - newestBucket.getTailWindowSize()
                    newestBucket.wasCounted = true
                    addNewBucket(startTime = newestBucket.endTime) // starts where old one ends
                    newestBucket = statsRingBuffer.peekTail()
                } else {
                    break
                }
            }

            assert(!newestBucket.wasCounted)
            assert(tsdatum.timestamp >= newestBucket.startTime && tsdatum.timestamp <= newestBucket.endTime)
            totalWindowAdded += newestBucket.add(tsdatum)

            fastStatsMutex.withLock {
                fastStats.apply {
                    this.n += 1
                    this.total += tsdatum.value
                    this.mean = this.total / this.n
                    this.windowSize += totalWindowAdded
                }
            }
        }
    }

    private suspend fun updateStats() {
        val n: Int
        val meanValue: Double
        val listCopy: List<TimeSeriesQueue>
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
            val newestTime = statsRingBuffer.peekTail().getTailNewestTime()
            val oldestTimeAllowed = newestTime - targetWindowSize
            val oldestBucket = statsRingBuffer.peekHead()
            val removed = oldestBucket.trimOlderThan(oldestTimeAllowed) // CPU intensive, potentially
            val oldestTime = oldestBucket.getHeadOldestTime()
            val absoluteWindowSize = newestTime - oldestTime
            assert(oldestTime >= oldestTimeAllowed)
            assert(newestTime - oldestTimeAllowed == targetWindowSize)
            assert(absoluteWindowSize <= targetWindowSize)
            listCopy = statsRingBuffer.asList()

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
            assert(fastStats.n == listCopy.sumOf { it.getCount() })
            stddev = sqrt(listCopy.sumOf { it.getSumOfSquaredVariances(meanValue) } / n)
            minValue = listCopy.minOf { it.getMin() }
            maxValue = listCopy.maxOf { it.getMax() }

            if (statsRingBuffer.getSize() >= numBuckets)
                hasUpdatedAfterWindowFilled = true
        }

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
