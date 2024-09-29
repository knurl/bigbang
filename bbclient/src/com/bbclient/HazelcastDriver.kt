package com.bbclient

import java.util.concurrent.*
import java.util.concurrent.ThreadPoolExecutor.AbortPolicy
import java.util.concurrent.atomic.AtomicBoolean

class HazelcastDriver(
    name: String,
    private val runnablesList: RunnablesList,
    private val statsFrequencyMillis: Long
) : Thread(), AutoCloseable {
    val logger: Logger = Logger(name)
    private val pool: ExecutorService

    private var isDraining = AtomicBoolean(false)

    private fun setDrain() {
        isDraining.set(true)
    }

    /*
     * Constructor and non-synchronized
     */
    init {
        val numThreads = if (Main.localTestMode) 2 else 6
        val numThreadsMax = (if (Main.localTestMode) 2 else 8) * numThreads
        val threadQueueSize = numThreadsMax * 2
        val keepAliveTimeSec = 60 // seconds

        this.pool = ThreadPoolExecutor(
            numThreads, numThreadsMax,
            keepAliveTimeSec.toLong(), TimeUnit.SECONDS,
            ArrayBlockingQueue(threadQueueSize),
            AbortPolicy()
        )
    }

    fun submit(runnable: Runnable) {
        var submitted = false
        val threadpoolSubmitBackoffMillis = 250 // ms
        while (!isDraining.get() && !submitted) {
            try {
                pool.submit(runnable)
                submitted = true
            } catch (e: RejectedExecutionException) {
                try {
                    sleep(threadpoolSubmitBackoffMillis.toLong())
                } catch (e2: InterruptedException) {
                    logger.log("*** RECEIVED INTERRUPTED EXCEPTION [SUBMIT] *** $e2")
                    currentThread().interrupt()
                }
            }
        }
    }

    override fun run() {
        logger.log("Starting up operations")
        val statsStopwatch = Stopwatch(statsFrequencyMillis)

        while (!isDraining.get()) {
            for (runnable in runnablesList) {
                if (isDraining.get()) break
                submit(runnable)
                if (!isDraining.get() && statsStopwatch.isTimeOver()) {
                    logger.log("STATS => " + runnablesList.listRunnablesToStatsString())
                }
            }
        }
    }

    fun reachedMinimumStatsPopulation(): Boolean {
        return runnablesList.stream().allMatch { obj: IMapMethodRunnable -> obj.hasReachedMinimumPopulation() }
    }

    @Throws(InterruptedException::class)
    private fun drain() {
        setDrain()
        pool.shutdown()
        if (!pool.awaitTermination(2, TimeUnit.SECONDS)) {
            logger.log("Timed out waiting for termination in drain()")
            pool.shutdownNow()
        }
    }

    fun drainAndJoin() {
        try {
            drain()
            this.join()
        } catch (e: InterruptedException) {
            throw RuntimeException(e)
        }
    }

    fun drainAndGetStats(): String {
        try {
            drain()
            return runnablesList.listRunnablesToCSV()
        } catch (e: InterruptedException) {
            logger.log("*** RECEIVED EXCEPTION [GET] *** $e")
            throw RuntimeException(e)
        }
    }

    override fun close() {
        try {
            drain()
        } catch (e: InterruptedException) {
            pool.shutdownNow()
            currentThread().interrupt()
        }
        pool.shutdownNow()

        for (runnable in runnablesList) {
            runnable.close()
        }
    }
}
