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

class TimeSeriesStats(
    windowSizeMillis: Long,
    private val updateSlowStats: Boolean = true,
    private val enableMetrics: Boolean = true): AutoCloseable {
    private val numBuckets = 10
    private val targetWindowSize = windowSizeMillis.milliseconds
    private val bucketDuration = targetWindowSize.div(numBuckets)
    private val timeSource = TimeSource.Monotonic
    /* Channel for new insertions */
    private val submitChannelBuffer = 64
    private val submitChannel = Channel<Double>(submitChannelBuffer)

    var hasUpdatedAfterWindowFilled = false
        private set

    data class TimeSeriesData(val timestamp: TimeMark, val value: Double)

    /* Protected by a mutex */
    private val statsRingBuffer = RingBuffer<TimeSeriesQueue>(capacity = numBuckets + 1)

    /*
     * Data class that collects all statistics together. These are protected by a MutableStateFlow
     */

    data class StatsGroup(
        var n: Int,
        var total: Double,
        var mean: Double,
        var windowSize: Duration,
        var windowFullPercentage: Int,
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
            windowFullPercentage = 0,
            stddev = 0.0,
            minValue = 0.0,
            maxValue = 0.0
        )
    )

    /*
     * Jobs object to keep track of all the coroutine jobs we automatically start.
     */

    private val jobs = object {
        private fun createCoroutineScope(name: String) = CoroutineScope(
            Job() +
                    Dispatchers.Default.limitedParallelism(1) +
                    CoroutineName(name))

        private val submitConsumerScope = createCoroutineScope("submitConsumer")
        private val metricsReporterScope = createCoroutineScope("metricsReporter")

        var metricsReporterJob: Job? = null

        init {
            if (enableMetrics)
                metricsReporterJob = metricsReporterScope.launch { metricsReporterLoop() }
        }

        val submitConsumerJob = submitConsumerScope.launch { submitConsumerLoop() }

        fun close() {
            runBlocking {
                submitConsumerJob.cancelAndJoin()
                submitConsumerScope.cancel()
                metricsReporterJob?.cancelAndJoin()
                metricsReporterScope.cancel()
                submitChannel.close()
            }
        }
    }

    /*
     * Functions that handle the producer/consumer processing of requests.
     */

    suspend fun submit(value: Double) {
        submitReporter.insert {
            submitChannel.send(value)
        }
    }

    fun submitBlocking(value: Double) {
        runBlocking {
            submit(value)
        }
    }

    private suspend fun submitConsumerLoop() {
        while (true) {
            val nextValue = submitChannel.receive()
            addReporter.insert {
                add(TimeSeriesData(timestamp = timeSource.markNow(), value = nextValue))
            }
        }
    }

    private suspend fun metricsReporterLoop() {
        while (true) {
            delay(4000)
            Reporters.reportAll()
        }
    }

    override fun close() {
        jobs.close()
    }

    /*
     * Internal metrics collection and reporting, to check performance.
     */
    object Reporters {
        private val logger = Logger("Metrics")
        private val reporters = mutableMapOf<String, Reporter>()

        class Reporter(private val name: String) {
            // Items related to ring buffer
            private val ringsize = 64
            private val metricsMutex = Mutex()
            private val metricsRing = RingBuffer<Duration>(ringsize)
            private var total = 0.seconds

            // Items related to emitting the average value
            private val average = MutableStateFlow(total)

            fun report(): String = "$name -> %.2fµs".format(average.value)

            suspend fun insert(action: suspend () -> Unit) {
                val timeTaken = measureTime { action() }
                metricsMutex.withLock {
                    if (!metricsRing.hasCapacity())
                        total -= metricsRing.dequeue()
                    metricsRing.enqueue(timeTaken)
                    total += timeTaken
                    average.update { total / metricsRing.size }
                }
            }
        }

        init {
            fun addReporter(name: String) {
                reporters[name] = Reporter(name)
            }
            addReporter("add")
            addReporter("update")
            addReporter("submit")
        }

        fun getNolock(name: String) = reporters[name]!!

        fun reportAll() {
            val reports = reporters.values.map { it.report() }
            logger.log(reports.joinToString(separator = " | "))
        }
    }

    private val addReporter = Reporters.getNolock("add")
    private val updateReporter = Reporters.getNolock("update")
    private val submitReporter = Reporters.getNolock("submit")

    private suspend fun add(tsdatum: TimeSeriesData) {
        fun addToFastStats(increaseN: Int, increaseTotal: Double, increaseWindowSize: Duration) {
            statsFlow.update { previous ->
                previous.copy(
                    n = previous.n + increaseN,
                    total = previous.total + increaseTotal,
                    windowSize = previous.windowSize + increaseWindowSize,
                    windowFullPercentage = min(100, (statsRingBuffer.size.toDouble() * 100.0 / numBuckets.toDouble()).toInt())
                )
            }
            statsFlow.update { latest -> latest.copy(mean = latest.total / latest.n) }
        }
        fun removeBucketAtHead() {
            val removed = statsRingBuffer.dequeue()
            addToFastStats(-removed.getCount(), -removed.getTotal(), -bucketDuration)
            assert(statsFlow.value.windowSize <= targetWindowSize)
        }

        fun addBucketAtTail(startTime: TimeMark) {
            // This new bucket is empty, so it doesn't yet affect our fast stats
            statsRingBuffer.enqueue(
                TimeSeriesQueue(
                    startTime = startTime,
                    endTime = startTime + bucketDuration
                )
            )
        }

        // If the ring buffer is empty, create a new bucket
        if (statsRingBuffer.isEmpty())
            addBucketAtTail(startTime = tsdatum.timestamp)

        // Is our new item too new for our newest bucket? If so make a new one
        var newestBucket = statsRingBuffer.peekTail()

        /*
         * If we can't fit newest timestamp into tail bucket, then we need to
         * dequeue the head bucket and enqueue a fresh new bucket. But before we do
         * that, this is the time to recalculate the slow-generating parameters since
         * we have no partial buckets at head or tail (which add to CPU cost in terms
         * of calculation).
         */
        if (tsdatum.timestamp > newestBucket.endTime) {
            statsFlow.update { previous ->
                previous.copy(windowSize = previous.windowSize + bucketDuration - newestBucket.getTailWindowSize())
            }
            newestBucket.setWasCounted()
            if (!statsRingBuffer.hasCapacity())
                removeBucketAtHead()
            if (updateSlowStats) {
                assert(!statsRingBuffer.isEmpty())
                updateReporter.insert { updateStats() }
            }
            addBucketAtTail(startTime = newestBucket.endTime)
            newestBucket = statsRingBuffer.peekTail()
        }

        assert(!newestBucket.getWasCounted())
        assert(tsdatum.timestamp >= newestBucket.startTime && tsdatum.timestamp <= newestBucket.endTime)

        /*
         * Add in the new datapoint, and increase the window size according to how much past
         * the beginning of the start point the new datapoint is.
         */
        val newWindowSizeIncrease = newestBucket.add(tsdatum)
        addToFastStats(1, tsdatum.value, newWindowSizeIncrease)
    }

    private fun checkFastStats() {
        assert(!statsRingBuffer.isEmpty())

        statsFlow.value.let { current ->
            assert(current.n == statsRingBuffer.sumOf { x -> x.getCount() })
            assert(current.total == statsRingBuffer.sumOf { x -> x.getTotal() })
            assert(current.mean == current.total / current.n)
        }
    }

    private fun updateStats() {
        /*
         * This fun should only be called if we have all full buckets with no partial buckets
         */
        assert(!statsRingBuffer.isEmpty())
        assert(statsRingBuffer.peekTail().getWasCounted())
        assert(statsRingBuffer.size <= numBuckets)

        checkFastStats()

        /*
         * Here we update the "slow" (heavy calculation) stats, and ensure the fast stats are accurate
         */
        statsFlow.value.let { current ->
            assert(current.windowSize == bucketDuration * statsRingBuffer.size) // should be the case when we have all full buckets
            statsFlow.update { latest ->
                latest.copy(
                    stddev = sqrt(statsRingBuffer.sumOf { x -> x.getSumOfSquaredVariances(latest.mean) } / latest.n),
                    minValue = statsRingBuffer.minOf { x -> x.getMin() },
                    maxValue = statsRingBuffer.maxOf { x -> x.getMax() }
                )
            }
        }

        if (statsRingBuffer.size >= numBuckets)
            hasUpdatedAfterWindowFilled = true
    }

    // This fun is threadsafe because it consumes from a MutableStateFlow
    fun toStatsString(): String {
        val stringList = mutableListOf<String>()
        runBlocking {
            statsFlow.value.let { current ->
                val windowFullPct = current.windowFullPercentage
                stringList.add("N=%,d".format(current.n))

                if (current.n > 0) {
                    val rate = current.n.toDouble() * 1_000.0 / current.windowSize.inWholeMilliseconds.toDouble()
                    stringList.add("R=%,.1f/s".format(rate))
                    stringList.add("W=%,dms".format(current.windowSize.inWholeMilliseconds))

                    if (!hasUpdatedAfterWindowFilled && windowFullPct < 100)
                        stringList.add("WFP=%d%%".format(windowFullPct))

                    if (hasUpdatedAfterWindowFilled) {
                        stringList.add(
                            "µ=%s σ=%s [%s⇠⇢%s]".format(
                                millisToString(current.mean),
                                millisToString(current.stddev),
                                millisToString(current.minValue),
                                millisToString(current.maxValue)
                            )
                        )
                    }
                }
            }
        }
        return stringList.joinToString(separator = " ")
    }

    // This fun is threadsafe because it consumes from a MutableStateFlow.
    fun toCSV() = runBlocking {
        statsFlow.value.let { current ->
            listOf(
                current.n,
                current.mean,
                current.stddev,
                current.minValue,
                current.maxValue
            ).joinToString(separator=",")
        }
    }
}
