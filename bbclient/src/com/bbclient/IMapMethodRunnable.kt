package com.bbclient

import com.hazelcast.map.IMap
import java.time.Duration
import java.time.Instant

abstract class IMapMethodRunnable internal constructor(
    @JvmField protected val map: IMap<Int?, String?>,
    private val methodName: String,
    private val quiet: Boolean
) : Runnable, AutoCloseable {
    private val logger = Logger(methodName)
    private var numFailed = 0
    private var windowSizeMillis: Long = 0
    private var stats: TimeSeriesStats

    init {
        if (!Main.localTestMode) this.windowSizeMillis = 60000
        else this.windowSizeMillis = 30000

        this.stats = TimeSeriesStats(this.windowSizeMillis, !quiet, false)
    }

    override fun close() {
        stats.close()
    }

    private fun add(value: Double) {
        stats.submitBlocking(value)
    }

    /*
     * TODO: Technically the following two functions change shared mutable state,
     *       but in the first case the value is monotonically increasing, and in the
     *       second it's a pointer swap, so we should be Ok for both.
     */
    fun hasReachedMinimumPopulation(): Boolean {
        return stats.hasUpdatedAfterWindowFilled
    }

    fun clearStats() {
        stats.close()
        stats = TimeSeriesStats(this.windowSizeMillis, !this.quiet, false)
    }

    override fun toString(): String {
        return "$methodName()"
    }

    @Synchronized
    fun toStatsString(): String {
        var failedString = ""
        if (numFailed > 0) failedString = "[%d FAILED]".format(numFailed)
        return "%s->{%s}%s".format(this, stats.toStatsString(), failedString)
    }

    @Synchronized
    fun toCSV(): String {
        return stats.toCSV()
    }

    abstract fun invokeMethod()

    override fun run() {
        val start = Instant.now()
        var finish: Instant?
        try {
            invokeMethod()
            finish = Instant.now()
        } catch (ex: Throwable) {
            finish = Instant.now()
            numFailed++
            logger.log(
                "*** EXCEPTION [%s] *** %s".format(
                    methodName,
                    ex.javaClass.simpleName
                )
            )
        }

        val runtime = Duration.between(start, finish).toMillis()
        add(runtime.toDouble())
    }
}
