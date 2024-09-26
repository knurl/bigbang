package com.bbclient

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlin.time.Duration.Companion.seconds
import kotlin.time.measureTime

class TimeSeriesStatsTest {
    private var windowSizeMillis = 3_000L
    private val stats = TimeSeriesStats(windowSizeMillis, true)
    private val logger = Logger("TimeSeriesTest", addTimestamp = true)

    fun startTest() {
        var averageCount = 0
        var averageTotal = 0.seconds

        runBlocking {
            launch(Dispatchers.Default) {
                while (true) {
                    averageTotal += measureTime {
                        stats.submit(1.0)
                    }
                    averageCount++
                    delay(5)
                }
            }

            launch(Dispatchers.Default) {
                while(true) {
                    delay(1000)
                    logger.log(stats.toStatsString())
                    val average = averageTotal / averageCount
                    logger.log("Average time per add() call is ${average.inWholeMicroseconds}µs")
                }
            }
        }
    }
}
