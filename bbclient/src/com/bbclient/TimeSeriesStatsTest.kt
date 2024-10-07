package com.bbclient

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlin.time.Duration.Companion.seconds
import kotlin.time.measureTime

class TimeSeriesStatsTest {
    private var windowSizeMillis = 3_000L
    private val stats1 = TimeSeriesStats(windowSizeMillis)
    private val stats2 = TimeSeriesStats(windowSizeMillis)
    private val logger = Logger("TimeSeriesTest", addTimestamp = true)

    fun startTest() {
        var averageCount = 0
        var averageTotal = 0.seconds

        runBlocking {
            launch(Dispatchers.Default) {
                while (true) {
                    averageTotal += measureTime {
                        stats1.submit(1.0)
                    }
                    averageCount++
                    delay((1L..10L).random())
                }
            }

            launch(Dispatchers.Default) {
                while (true) {
                    averageTotal += measureTime {
                        stats2.submit(1.0)
                    }
                    averageCount++
                    delay((5L..50L).random())
                }
            }

            launch(Dispatchers.Default) {
                while(true) {
                    delay(1000)
                    logger.log("stats1=${stats1.toStatsString()} / stats2=${stats2.toStatsString()}")
                }
            }
        }
    }
}
