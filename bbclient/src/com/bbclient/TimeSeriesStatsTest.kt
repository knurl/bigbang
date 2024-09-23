package com.bbclient.com.bbclient

import com.bbclient.TimeSeriesStats
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import java.text.SimpleDateFormat
import java.util.*
import java.util.concurrent.ThreadLocalRandom

class TimeSeriesStatsTest {
    private val stats = TimeSeriesStats(5_000)

    fun startTest() {
        val updatePeriodMillis = 1_000L
        val rand = ThreadLocalRandom.current()
        val formatter = SimpleDateFormat("HH:mm:ss.SS")

        runBlocking {
            stats.startAutoUpdate()

            launch {
                while (true) {
                    stats.add(rand.nextDouble(0.0, 100.0))
                    delay(rand.nextLong(5, 25))
                }
            }

            repeat(100) {
                delay(updatePeriodMillis)
                launch {
                    val current = formatter.format(Calendar.getInstance().time).toString()
                    println("$current $stats")
                }
            }
        }
    }
}
