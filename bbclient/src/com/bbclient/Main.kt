package com.bbclient

import com.hazelcast.client.HazelcastClient
import com.hazelcast.client.config.ClientConfig
import com.hazelcast.client.impl.connection.tcp.RoutingMode
import com.hazelcast.cluster.Cluster
import com.hazelcast.core.HazelcastInstance
import com.hazelcast.map.IMap
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import java.time.Duration
import java.time.Instant
import java.util.function.Consumer
import kotlin.time.Duration.Companion.seconds

private const val portNumber: Int = 4000

internal object Main {
    private var statsUnitTest: Boolean = false
    var localTestMode: Boolean = false

    private val logger = Logger("Main")

    private fun createMapAndGetLastKey(
        map: IMap<Int?, String?>,
        numEntries: Int,
        mapValueSize: Int
    ): KeyBoundary {
        logger.log("Clearing map")
        map.clear()
        logger.log("Map is cleared")

        logger.log(
            "+++ TARGET MAP SIZE -> %,d (approx %,.1fMB) +++".format(
                numEntries,
                numEntries.toDouble() * mapValueSize / 1024 / 1024
            )
        )

        val firstKey = Int.MIN_VALUE
        val setRunnable = SetRunnable(map, mapValueSize, firstKey)
        val runnablesList = RunnablesList()
        runnablesList.add(setRunnable)

        val fullnessCheckStopwatch = Stopwatch(1.seconds)

        val statsFrequency = 2.seconds

        HazelcastDriver("maploader", runnablesList, statsFrequency).use { mapLoaderDriver ->
            mapLoaderDriver.start() // start sending the set commands to Hazelcast as fast as allowable

            var mapSize: Long = 0

            while (mapSize < numEntries) {
                if (fullnessCheckStopwatch.isTimeOver()) {
                    mapSize = map.size.toLong()
                    logger.log("MAPSIZE=%,d".format(mapSize))
                }
            }

            logger.log("+++ ACTUAL MAP SIZE -> %,d +++".format(mapSize))
            return KeyBoundary(firstKey, setRunnable.lastKey)
        }
    }

    private fun millisBetween(begin: Instant, end: Instant): Long {
        return Duration.between(begin, end).toMillis()
    }

    private fun secondsBetween(begin: Instant, end: Instant?): Long {
        return Duration.between(begin, end).toSeconds()
    }

    enum class TestStage {
        MINPOP,
        GOTOCHAOSSTART,
        CHAOSSTARTED,
        GOTOCHAOSSTOP,
        CHAOSSTOPPED,
        DRAIN,
        REPORTED,
        FINISHED
    }

    @Throws(InterruptedException::class)
    @JvmStatic
    fun main(args: Array<String>) = runBlocking {
        if (statsUnitTest) {
            val statsTest = TimeSeriesStatsTest()
            statsTest.startTest()
        }
        val maxEntries: Int
        val mapValueSize: Int
        if (!localTestMode) {
            maxEntries = 1 shl 17
            mapValueSize = 1 shl 15
        } else {
            maxEntries = 1 shl 10
            mapValueSize = 1 shl 3
        }
        logger.log("Map: maxEntries=%,d mapValueSize=%,d".format(maxEntries, mapValueSize))
        val socketResponseResponder = SocketResponseResponder()

        // all in microseconds, which we use as a standard
        val timeInChaosStarted = if (localTestMode) 30000 else 70000
        val timeInChaosStopped = 30000L // used only in test mode
        val statsReportFrequency = 4.seconds
        val stateChangeCheckFrequency = 1.seconds
        val migrationsCheckFrequency = 4.seconds
        val stateChangeStopwatch = Stopwatch(stateChangeCheckFrequency) // ms
        val migrationsCheckStopwatch = Stopwatch(migrationsCheckFrequency) // ms

        /* Spawn a thread to take input on a port */
        logger.log("Creating Socket Listener Thread")
        val socketListenerThread = SocketListenerThread(socketResponseResponder, portNumber)
        logger.log("Starting Socket Listener Thread")
        socketListenerThread.start()

        var client: HazelcastClientManager? = null
        var embeddedCluster: EmbeddedHazelcastCluster? = null
        if (localTestMode) {
            embeddedCluster = EmbeddedHazelcastCluster(3)
        } else {
            val memberAddress = socketResponseResponder.awaitMemberAddress()
            logger.log("*** IP ADDRESS for dev-0 is %s ***".format(memberAddress))
            logger.log("Setting up client connection and client state listener")
            client = HazelcastClientManager(memberAddress)
        }

        /*
         * Now set up listeners for migration and membership state with the cluster.
         * We must register listeners or the events will not automatically flow through to us.
         */
        logger.log("Registering membership and migration event listeners with cluster")
        val instance: HazelcastInstance
        val cluster: Cluster
        if (client != null) {
            instance = client.hazelcastInstance
            cluster = client.hazelcastInstance.cluster
        } else {
            checkNotNull(embeddedCluster)
            instance = embeddedCluster.getInstance(0)
            cluster = embeddedCluster.cluster
            assert(cluster.members.size == 3)
        }

        val numMembers = cluster.members.size
        val clientMembershipListener = ClientMembershipListener(numMembers)
        val clientMigrationListener = ClientMigrationListener()
        cluster.addMembershipListener(clientMembershipListener)

        while (clientMembershipListener.clusterIsMissingMembers()) {
            logger.log("Cluster is missing members. Waiting for cluster to form.")
            delay(1000)
        }

        instance.partitionService.addMigrationListener(clientMigrationListener)

        logger.log("Creating new map")
        val map = instance.getMap<Int, String>("map")
        val keyBoundary = createMapAndGetLastKey(map, maxEntries, mapValueSize)

        logger.log("Setting up stats capture objects for Hz operations")
        val runnablesList = RunnablesList()
        runnablesList.add(IsEmptyRunnable(map))
        runnablesList.add(PutIfAbsentRunnable(map, mapValueSize, keyBoundary.firstKey, keyBoundary.lastKey))
        val allHzMethodNames = java.lang.String.join(", ",
            runnablesList.stream().map { obj: IMapMethodRunnable -> obj.toString() }.toList()
        )

        var statsCsvBeforeChaos: String? = ""
        var statsAfterChaos = ""
        var chaosStartTime: Instant? = null
        var timeMigrationEnded: Instant? = null

        val logger = Logger("Test Driver", "***")
        logger.log("STARTING TEST DRIVER")
        var stage = TestStage.MINPOP
        HazelcastDriver("latencyTest", runnablesList, statsReportFrequency).use { driver ->
            driver.start() // start sending those runnables against Hazelcast on repeat

            logger.log("Running %s operations against hazelcast map".format(allHzMethodNames))
            logger.log("Will continue until min stats population reached for each operation")

            while (stage != TestStage.DRAIN) {
                /* If there were any migrations previously reported, or we just
             * observed a large timeout, check on the cluster health and see
             * if we're running any migrations currently.
             */
                if (migrationsCheckStopwatch.isTimeOver()) {
                    clientMembershipListener.logCurrentMembershipIfMissingMembers()
                    clientMigrationListener.logAnyActiveMigrations()
                }

                if (stateChangeStopwatch.isTimeOver()) {
                    chaosStartTime = socketResponseResponder.chaosStartTime
                    timeMigrationEnded = clientMigrationListener.instantEndOfLastMigration

                    // See if we're ready to start testing
                    stage = when (stage) {
                        TestStage.MINPOP -> {
                            if (driver.reachedMinimumStatsPopulation()) {
                                logger.log("Capturing stats with good network")
                                statsCsvBeforeChaos = runnablesList.listRunnablesToCSV()
                                logger.log("Stats with min pop reached: " + runnablesList.listRunnablesToStatsString(), plain = true)

                                // Signal to client that we are ready to proceed
                                socketResponseResponder.setIsReadyForChaosStart()
                                if (localTestMode) {
                                    Thread.sleep(25000)
                                    socketResponseResponder.setChaosStartTime()
                                }
                                TestStage.GOTOCHAOSSTART
                            } else {
                                stage
                            }
                        }

                        TestStage.GOTOCHAOSSTART -> {
                            if (chaosStartTime != null) { // client has started chaos!
                                // Block client from starting next iteration until we are done this test iteration
                                socketResponseResponder.setIsNotReadyForChaosStart()
                                // Clear stats as chaos testing has started
                                logger.log("Resetting stats after starting chaos")
                                runnablesList.forEach { x -> x.clearStats() }
                                logger.log("Stats after reset: " + runnablesList.listRunnablesToStatsString(), plain = true)
                                TestStage.CHAOSSTARTED
                            } else {
                                stage
                            }
                        }

                        TestStage.CHAOSSTARTED -> {
                            if (millisBetween(chaosStartTime!!, Instant.now()) >= timeInChaosStarted) {
                                logger.log("Driver signaling chaos start period should end")
                                socketResponseResponder.setIsNotReadyForChaosStart()
                                socketResponseResponder.setIsReadyForChaosStop()
                                if (localTestMode) {
                                    socketResponseResponder.setIsChaosStopped()
                                }
                                TestStage.GOTOCHAOSSTOP
                            } else {
                                stage
                            }
                        }

                        TestStage.GOTOCHAOSSTOP -> {
                            if (socketResponseResponder.isChaosStopped) {
                                socketResponseResponder.setIsNotReadyForChaosStop()
                                logger.log("Chaos stopped -> waiting for migration completion")
                                if (localTestMode) {
                                    launch {
                                        delay(timeInChaosStopped)
                                        clientMigrationListener.setMigrationFinished()
                                    }
                                }
                                TestStage.CHAOSSTOPPED
                            } else {
                                stage
                            }
                        }

                        TestStage.CHAOSSTOPPED -> {
                            if (timeMigrationEnded != null &&
                                !clientMigrationListener.isMigrationActive &&
                                !clientMembershipListener.clusterIsMissingMembers()
                            ) {
                                logger.log("Draining remaining tasks")
                                statsAfterChaos = driver.drainAndGetStats()
                                TestStage.DRAIN
                            } else {
                                stage
                            }
                        }

                        else -> {
                            stage
                        }
                    }
                }
            }
            while (stage != TestStage.FINISHED) {
                stage = when (stage) {
                    TestStage.DRAIN -> {
                        checkNotNull(chaosStartTime)
                        logger.log("Clearing last migration and sending test results")
                        val testResult = java.lang.String.join(
                            ",", listOf(
                                maxEntries.toString(),
                                mapValueSize.toString(),
                                timeInChaosStarted.toString(),
                                secondsBetween(chaosStartTime!!, timeMigrationEnded).toString(),
                                statsCsvBeforeChaos,
                                statsAfterChaos
                            )
                        )
                        socketResponseResponder.setTestResult(testResult)
                        clientMigrationListener.clearLastMigration()
                        if (localTestMode) socketResponseResponder.setIsTestResultReceived()
                        TestStage.REPORTED
                    }

                    TestStage.REPORTED -> {
                        if (socketResponseResponder.isTestResultReceived) {
                            logger.log("Client received test results -> driver finished")
                            runnablesList.forEach(Consumer { obj: IMapMethodRunnable -> obj.clearStats() })
                            socketResponseResponder.resetTest()
                            statsCsvBeforeChaos = null
                            TestStage.FINISHED
                        } else {
                            stage
                        }
                    }

                    else -> stage
                }
            }
        }

        assert(stage == TestStage.FINISHED)
        delay(1000)
    }

    @JvmRecord
    internal data class KeyBoundary(val firstKey: Int, val lastKey: Int)

    internal class HazelcastClientManager(memberAddress: String) {
        val hazelcastInstance: HazelcastInstance

        init {
            /*
         * Client configuration. We set up a ClientStateListener here so that we can block
         * until the client is connected to the Hazelcast cluster.
         */
            val clientConfig = ClientConfig()
            val networkConfig = clientConfig.networkConfig
            networkConfig.clusterRoutingConfig.setRoutingMode(RoutingMode.SINGLE_MEMBER)
            clientConfig.connectionStrategyConfig.setAsyncStart(true)
            networkConfig.setAddresses(ArrayList(listOf(memberAddress)))
            this.hazelcastInstance = HazelcastClient.newHazelcastClient(clientConfig)
        }
    }
}
