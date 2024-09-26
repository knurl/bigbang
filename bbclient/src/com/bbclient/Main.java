package com.bbclient;

import com.hazelcast.client.config.ClientConfig;
import com.hazelcast.client.impl.connection.tcp.RoutingMode;
import com.hazelcast.cluster.Cluster;
import com.hazelcast.core.HazelcastInstance;
import com.hazelcast.map.IMap;

import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

class Main {
    public static boolean statsUnitTest = true;
    public static boolean localTestMode = true;
    static final int portNumber = 4000;

    private final static Logger logger = new Logger("Main");

    record KeyBoundary(Integer firstKey, Integer lastKey) {}

    private static KeyBoundary createMapAndGetLastKey(IMap<Integer, String> map,
                                                      int numEntries,
                                                      int mapValueSize) {
        logger.log("Clearing map");
        map.clear();
        logger.log("Map is cleared");

        logger.log("+++ TARGET MAP SIZE -> %,d (approx %,.1fMB) +++".formatted(numEntries,
                (double) numEntries * mapValueSize / 1024 / 1024));

        final var firstKey = Integer.MIN_VALUE;
        SetRunnable setRunnable = new SetRunnable(map, mapValueSize, firstKey);
        var runnablesList = new RunnablesList();
        runnablesList.add(setRunnable);

        final int fullnessCheckTimeoutMillis = 1_000; // ms
        var fullnessCheckStopwatch = new Stopwatch(fullnessCheckTimeoutMillis);

        var statsFrequencyMillis = 4_000;

        try (var mapLoaderDriver = new HazelcastDriver("maploader", runnablesList, statsFrequencyMillis)) {
            mapLoaderDriver.start(); // start sending the set commands to Hazelcast as fast as allowable

            long mapSize = 0;

            while (mapSize < numEntries) {
                if (fullnessCheckStopwatch.isTimeOver()) {
                    mapSize = map.size();
                    logger.log("MAPSIZE=%,d".formatted(mapSize));
                }
            }

            logger.log("+++ ACTUAL MAP SIZE -> %,d +++".formatted(mapSize));
            mapLoaderDriver.drainAndJoin();
            return new KeyBoundary(firstKey, setRunnable.getLastKey());
        }
    }

    private static long millisBetween(Instant begin, Instant end) {
        return Duration.between(begin, end).toMillis();
    }

    private static long secondsBetween(Instant begin, Instant end) {
        return Duration.between(begin, end).toSeconds();
    }

    protected static class RunnablesList extends ArrayList<IMapMethodRunnable> {
        protected String listRunnablesToStatsString() {
            List<String> statsSummaries = new ArrayList<>();
            this.forEach(x -> statsSummaries.add(x.toStatsString()));
            return String.join("; ", statsSummaries);
        }

        protected String listRunnablesToCSV() {
            List<String> statsCSVs = new ArrayList<>();
            this.forEach(x -> statsCSVs.add(x.toCSV()));
            return String.join(",", statsCSVs);
        }
    }

    static class HazelcastClientManager {
        private final HazelcastInstance hazelcastInstance;

        HazelcastClientManager(String memberAddress) {
            /*
             * Client configuration. We set up a ClientStateListener here so that we can block
             * until the client is connected to the Hazelcast cluster.
             */
            ClientConfig clientConfig = new ClientConfig();
            var networkConfig = clientConfig.getNetworkConfig();
            networkConfig.getClusterRoutingConfig().setRoutingMode(RoutingMode.SINGLE_MEMBER);
            clientConfig.getConnectionStrategyConfig().setAsyncStart(true);
            networkConfig.setAddresses(new ArrayList<>(Collections.singletonList(memberAddress)));
            this.hazelcastInstance = com.hazelcast.client.HazelcastClient.newHazelcastClient(clientConfig);
        }

        HazelcastInstance getHazelcastInstance() {
            return this.hazelcastInstance;
        }
    }

    public static void main(String[] args) {
        if (statsUnitTest) {
            TimeSeriesStatsTest statsTest = new TimeSeriesStatsTest();
            statsTest.startTest();
        }
        final int maxEntries, mapValueSize;
        if (!localTestMode) {
            maxEntries = 1 << 17;
            mapValueSize = 1 << 15;
        } else {
            maxEntries = 1 << 10;
            mapValueSize = 1 << 3;
        }
        logger.log("Map: maxEntries=%,d mapValueSize=%,d".formatted(maxEntries, mapValueSize));
        var socketResponseResponder = new SocketResponseResponder();

        enum TestStage {
            MINPOP,
            GOTOCHAOSSTART,
            CHAOSSTARTED,
            GOTOCHAOSSTOP,
            CHAOSSTOPPED,
            DRAIN,
            REPORTED,
            FINISHED
        }

        // all in microseconds, which we use as a standard
        final int timeInChaosStarted = localTestMode ? 30000 : 70000;
        final int timeInChaosStopped = 30000; // used only in test mode
        final int statsReportFrequency = 4000;
        final int stateChangeCheckFrequency = 1000;
        final int migrationsCheckFrequency = 4000;
        var stateChangeStopwatch = new Stopwatch(stateChangeCheckFrequency); // ms
        var migrationsCheckStopwatch = new Stopwatch(migrationsCheckFrequency); // ms

        /* Spawn a thread to take input on a port */
        logger.log("Creating Socket Listener Thread");
        var socketListenerThread = new SocketListenerThread(socketResponseResponder, portNumber);
        logger.log("Starting Socket Listener Thread");
        socketListenerThread.start();

        HazelcastClientManager client = null;
        EmbeddedHazelcastCluster embeddedCluster = null;
        if (localTestMode) {
            embeddedCluster = new EmbeddedHazelcastCluster(3);
        } else {
            String memberAddress = socketResponseResponder.awaitMemberAddress();
            logger.log("*** IP ADDRESS for dev-0 is %s ***".formatted(memberAddress));
            logger.log("Setting up client connection and client state listener");
            client = new HazelcastClientManager(memberAddress);
        }

        /*
         * Now set up listeners for migration and membership state with the cluster.
         * We must register listeners or the events will not automatically flow through to us.
         */
        logger.log("Registering membership and migration event listeners with cluster");
        final HazelcastInstance instance;
        final Cluster cluster;
        if (client != null) {
            instance = client.getHazelcastInstance();
            cluster = client.getHazelcastInstance().getCluster();
        } else {
            assert embeddedCluster != null;
            instance = embeddedCluster.getInstance(0);
            cluster = embeddedCluster.getCluster();
            assert cluster.getMembers().size() == 3;
        }

        var numMembers = cluster.getMembers().size();
        var clientMembershipListener = new ClientMembershipListener(numMembers);
        var clientMigrationListener = new ClientMigrationListener();
        cluster.addMembershipListener(clientMembershipListener);

        while (clientMembershipListener.clusterIsMissingMembers()) {
            logger.log("Cluster is missing members. Waiting for cluster to form.");
            try {
                Thread.sleep(1000);
            } catch (InterruptedException e) {
                throw new RuntimeException(e);
            }
        }

        instance.getPartitionService().addMigrationListener(clientMigrationListener);

        logger.log("Creating new map");
        IMap<Integer, String> map = instance.getMap("map");
        var keyBoundary = createMapAndGetLastKey(map, maxEntries, mapValueSize);

        logger.log("Setting up stats capture objects for Hz operations");
        var runnablesList = new RunnablesList();
        runnablesList.add(new IsEmptyRunnable(map));
        runnablesList.add(new PutIfAbsentRunnable(map, mapValueSize, keyBoundary.firstKey(), keyBoundary.lastKey()));
        var allHzMethodNames = String.join(", ",
                runnablesList.stream().map(IMapMethodRunnable::toString).toList());

        String statsBeforeChaos = "", statsAfterChaos = "";
        Instant chaosStartTime = null, timeMigrationEnded = null;

        var logger = new Logger("Test Driver", "***");
        logger.log("STARTING TEST DRIVER");
        try (var hazelcastDriver = new HazelcastDriver("latencyTest", runnablesList, statsReportFrequency)) {
            hazelcastDriver.start(); // start sending those runnables against Hazelcast on repeat
            var testStage = TestStage.MINPOP;

            logger.log("Running %s operations against hazelcast map".formatted(allHzMethodNames));
            logger.log("Will continue until min stats population reached for each operation");

            while (testStage != TestStage.DRAIN) {
                /* If there were any migrations previously reported, or we just
                 * observed a large timeout, check on the cluster health and see
                 * if we're running any migrations currently.
                 */
                if (migrationsCheckStopwatch.isTimeOver()) {
                    clientMembershipListener.logCurrentMembershipIfMissingMembers();
                    clientMigrationListener.logAnyActiveMigrations();
                }

                if (stateChangeStopwatch.isTimeOver()) {
                    chaosStartTime = socketResponseResponder.getChaosStartTime();
                    timeMigrationEnded = clientMigrationListener.getInstantEndOfLastMigration();

                    // See if we're ready to start testing
                    testStage = switch (testStage) {
                        case MINPOP -> {
                            if (hazelcastDriver.reachedMinimumStatsPopulation()) {
                                logger.log("Capturing stats with good network");
                                statsBeforeChaos = runnablesList.listRunnablesToCSV();
                                // Signal to client that we are ready to proceed
                                socketResponseResponder.setIsReadyForChaosStart();
                                if (localTestMode) {
                                    Thread.sleep(10000);
                                    socketResponseResponder.setChaosStartTime();
                                }
                                yield TestStage.GOTOCHAOSSTART;
                            } else {
                                yield testStage;
                            }
                        }
                        case GOTOCHAOSSTART -> {
                            if (chaosStartTime != null) { // client has started chaos!
                                // Block client from starting next iteration until we are done this test iteration
                                socketResponseResponder.setIsNotReadyForChaosStart();
                                // Clear stats as chaos testing has started
                                logger.log("Resetting stats after starting chaos");
                                runnablesList.forEach(IMapMethodRunnable::clearStats);
                                yield TestStage.CHAOSSTARTED;
                            } else {
                                yield testStage;
                            }
                        }
                        case CHAOSSTARTED -> {
                            if (millisBetween(chaosStartTime, Instant.now()) >= timeInChaosStarted) {
                                logger.log("Driver signaling chaos start period should end");
                                socketResponseResponder.setIsNotReadyForChaosStart();
                                socketResponseResponder.setIsReadyForChaosStop();
                                if (localTestMode)
                                    socketResponseResponder.setIsChaosStopped();
                                yield TestStage.GOTOCHAOSSTOP;
                            }
                            yield testStage;
                        }
                        case GOTOCHAOSSTOP -> {
                            if (socketResponseResponder.getIsChaosStopped()) {
                                socketResponseResponder.setIsNotReadyForChaosStop();
                                logger.log("Chaos stopped -> waiting for migration completion");
                                if (localTestMode)
                                    hazelcastDriver.submit(() ->
                                            clientMigrationListener.setMigrationFinishedAfterDelay(timeInChaosStopped));
                                yield TestStage.CHAOSSTOPPED;
                            }
                            yield testStage;
                        }
                        case CHAOSSTOPPED -> {
                            if (timeMigrationEnded != null &&
                                    !clientMigrationListener.isMigrationActive() &&
                                    !clientMembershipListener.clusterIsMissingMembers()) {
                                logger.log("Draining remaining tasks");
                                statsAfterChaos = hazelcastDriver.drainAndGetStats();
                                yield TestStage.DRAIN;
                            }
                            yield testStage;
                        }
                        default -> testStage;
                    };
                }
            }

            while (testStage != TestStage.FINISHED) {
                testStage = switch (testStage) {
                    case DRAIN -> {
                        assert chaosStartTime != null;
                        logger.log("Clearing last migration and sending test results");
                        var testResult = String.join(",", List.of(
                                String.valueOf(maxEntries),
                                String.valueOf(mapValueSize),
                                String.valueOf(timeInChaosStarted),
                                Long.toString(secondsBetween(chaosStartTime, timeMigrationEnded)),
                                statsBeforeChaos,
                                statsAfterChaos));
                        socketResponseResponder.setTestResult(testResult);
                        clientMigrationListener.clearLastMigration();
                        if (localTestMode)
                            socketResponseResponder.setIsTestResultReceived();
                        yield TestStage.REPORTED;
                    }
                    case REPORTED -> {
                        if (socketResponseResponder.getIsTestResultReceived()) {
                            logger.log("Client received test results -> driver finished");
                            runnablesList.forEach(IMapMethodRunnable::clearStats);
                            socketResponseResponder.resetTest();
                            statsBeforeChaos = null;
                            yield TestStage.FINISHED;
                        } else {
                            yield testStage;
                        }
                    }
                    default -> testStage;
                };
            }
        } catch (InterruptedException e) {
            throw new RuntimeException(e);
        }
    }
}
