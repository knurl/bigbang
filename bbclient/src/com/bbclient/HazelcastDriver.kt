package com.bbclient

import kotlinx.coroutines.*
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicInteger
import kotlin.time.Duration

class HazelcastDriver(
    name: String,
    private val runnablesList: RunnablesList,
    private val statsFrequency: Duration
) : AutoCloseable {
    val logger: Logger = Logger(name)

    private val driverScope = CoroutineScope(
        Job() +
                Dispatchers.Default +
                CoroutineName("Executor"))

    class DispatcherExecutor(private val maxConcurrency: Int): AutoCloseable {
        private var concurrency = AtomicInteger(0)

        private val executorScope = CoroutineScope(
            Job() +
                    Dispatchers.IO +
                    CoroutineName("DispatcherExecutor")
        )

        fun submit(f: suspend () -> Unit): Boolean {
            var submitted = false
            if (concurrency.incrementAndGet() <= maxConcurrency) {
                submitted = true
                executorScope.launch {
                    f()
                    concurrency.decrementAndGet()
                }
            } else {
                concurrency.decrementAndGet()
            }
            return submitted
        }

        override fun close() {
            runBlocking {
                executorScope.coroutineContext.job.cancelAndJoin()
                executorScope.coroutineContext.cancelChildren()
                executorScope.cancel()
            }
        }
    }

    private val maxConcurrency = if (Main.localTestMode) 16 else 32

    private val pool = DispatcherExecutor(maxConcurrency)

    private var isDraining = AtomicBoolean(false)

    private fun setDrain() {
        isDraining.set(true)
    }

    fun start() = driverScope.launch {
        logger.log("Starting up operations")
        val statsStopwatch = Stopwatch(statsFrequency)

        while (!isDraining.get()) {
            for (runnable in runnablesList) {
                var submitted = false
                while (!submitted && !isDraining.get()) {
                    submitted = pool.submit { runnable.run() }

                    if (!submitted)
                        delay(100)
                }

                if (statsStopwatch.isTimeOver() && !isDraining.get())
                        logger.log("STATS => " + runnablesList.listRunnablesToStatsString())
            }
        }
    }

    fun reachedMinimumStatsPopulation(): Boolean {
        return runnablesList.stream().allMatch { obj: IMapMethodRunnable -> obj.hasReachedMinimumPopulation() }
    }

    private fun drain() {
        runBlocking {
            setDrain()
            pool.close()
            driverScope.coroutineContext.job.cancelAndJoin()
            driverScope.cancel()
        }
    }

    fun drainAndGetStats(): String {
        drain()
        return runnablesList.listRunnablesToCSV()
    }

    override fun close() {
        drain()
        for (runnable in runnablesList) {
            runnable.close()
        }
    }
}
