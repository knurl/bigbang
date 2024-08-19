package com.bbclient;

import com.hazelcast.client.HazelcastClient;
import com.hazelcast.client.config.ClientConfig;
import com.hazelcast.client.impl.connection.tcp.RoutingMode;
import com.hazelcast.client.util.ClientStateListener;
import com.hazelcast.core.HazelcastInstance;
import com.hazelcast.map.IMap;
import org.apache.commons.math3.stat.descriptive.DescriptiveStatistics;

import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.*;
import java.util.function.Supplier;

class Main {
    public static boolean rapidTestMode = false;
    static final int portNumber = 4000;

    static final int mapValueSize = 1 << 16;
    private final static Logger logger = new Logger("Main");

    static void awaitConnected(ClientStateListener listener) {
        var backoff = 50; // ms

        while (true) {
            try {
                listener.awaitConnected();
                return;
            } catch (InterruptedException ex) {
                logger.log("*** RECEIVED EXCEPTION [AWAITCONN] *** %s"
                        .formatted(ex.getClass().getSimpleName()));
                backoff <<= 1;

                try {
                    Thread.sleep(backoff);
                } catch (InterruptedException ex2) {
                    logger.log(("*** RECEIVED EXCEPTION [SLEEPING] *** %s")
                            .formatted(ex2.getClass().getSimpleName()));
                    backoff <<= 1;
                }
            }
        }
    }

    private static class ThreadPool implements AutoCloseable {
        ExecutorService pool;

        static final int numThreads = 7;
        static final int numThreadsMax = 2*numThreads;
        static final int threadQueueSize = numThreadsMax;
        static final int keepAliveTimeSec = 60; // seconds

        public ThreadPool() {
            pool = new ThreadPoolExecutor(numThreads, numThreadsMax,
                    keepAliveTimeSec, TimeUnit.SECONDS,
                    new ArrayBlockingQueue<>(threadQueueSize),
                    new ThreadPoolExecutor.AbortPolicy());
        }

        public boolean submit(Runnable runnable) {
            boolean accepted;
            try {
                pool.submit(runnable);
                accepted = true;
            } catch (RejectedExecutionException e) {
                accepted = false;
            }
            return accepted;
        }

        public void close() {
            pool.shutdown();
            try {
                if (!pool.awaitTermination(60, TimeUnit.SECONDS))
                    pool.shutdownNow();
            } catch (InterruptedException e) {
                pool.shutdownNow();
                Thread.currentThread().interrupt();
            }
        }
    }

    record KeyBoundary(Integer firstKey, Integer lastKey) {}

    private static KeyBoundary createMapAndGetLastKey(ThreadPool threadPool,
                                                      ClientStateListener listener,
                                                      IMap<Integer, String> map,
                                                      long numEntries) throws InterruptedException {
        logger.log("Clearing map");
        awaitConnected(listener);
        map.clear();
        logger.log("Map is cleared");

        DescriptiveStatistics opsRateStats = new DescriptiveStatistics();

        logger.log("+++ TARGET MAP SIZE -> %,d (approx %,.1fMB) +++".formatted(numEntries,
                (double)numEntries*mapValueSize/1024/1024));

        final var firstKey = Integer.MIN_VALUE;
        SetRunnable setRunnable = new SetRunnable(map, mapValueSize, firstKey);

        long mapSize = 0;

        final long executorSubmitBackoff = 250; // ms
        final long fullnessCheckTimeout = 2_000; // ms
        var fullnessCheckStopwatch = new Stopwatch(fullnessCheckTimeout); // ms

        while (mapSize < numEntries) {
            awaitConnected(listener);

            if (fullnessCheckStopwatch.isTimeOver()) {
                mapSize = map.size();
                var opsRate = fullnessCheckStopwatch.ratePerSecond();
                opsRateStats.addValue(opsRate);
                logger.log("MAPSIZE=%,d OPSRATE=%,.2f/s".formatted(mapSize, opsRate));
                continue;
            }

            if (threadPool.submit(setRunnable))
                fullnessCheckStopwatch.addUnit();
            else
                Thread.sleep(executorSubmitBackoff);
        }

        logger.log("+++ ACTUAL MAP SIZE -> %,d +++".formatted(mapSize));
        return new KeyBoundary(firstKey, setRunnable.getLastKey());
    }

    private static long millisBetween(Instant begin, Instant end) {
        return Duration.between(begin, end).toMillis();
    }

    private static long secondsBetween(Instant begin, Instant end) {
        return Duration.between(begin, end).toSeconds();
    }

    protected static class MyRunnables extends ArrayList<IMapMethodRunnable> implements Supplier<String> {
        protected String listRunnablesToString() {
            List<String> statsSummaries = new ArrayList<>();
            this.forEach(x -> statsSummaries.add(x.toString()));
            return String.join("; ", statsSummaries);
        }

        protected String listRunnablesToCSV() {
            List<String> statsCSVs = new ArrayList<>();
            this.forEach(x -> statsCSVs.add(x.toCSV()));
            return String.join(",", statsCSVs);
        }

        public String get() {
            return listRunnablesToCSV();
        }
    }

    public static void main(String[] args) throws InterruptedException {
        var socketResponseResponder = new SocketResponseResponder();

        /* Spawn a thread to take input on a port */
        logger.log("Creating Socket Listener Thread");
        var socketListenerThread = new SocketListenerThread(socketResponseResponder, portNumber);
        logger.log("Starting Socket Listener Thread");
        socketListenerThread.start();

        String memberAddress = socketResponseResponder.awaitMemberAddress();

        /* Test mode
        socketResponseResponder.setIsReadyForTesting();
        socketResponseResponder.setIsTestingComplete("0,0,0,0");
         */

        ClientConfig clientConfig = new ClientConfig();
        var networkConfig = clientConfig.getNetworkConfig();
        networkConfig.addAddress(memberAddress);
        networkConfig.getClusterRoutingConfig().setRoutingMode(RoutingMode.SINGLE_MEMBER);
        ClientStateListener clientStateListener = new ClientStateListener(clientConfig);
        HazelcastInstance hazelcastInstanceClient = HazelcastClient.newHazelcastClient(clientConfig);
        var cluster = hazelcastInstanceClient.getCluster();
        var numMembers = cluster.getMembers().size();
        var clientMembershipListener = new ClientMembershipListener(numMembers);
        var clientMigrationListener = new ClientMigrationListener();
        logger.log("Registering ClientMembershipListener with cluster %s".formatted(cluster));
        cluster.addMembershipListener(clientMembershipListener);
        logger.log("Registering ClientMigrationListener with cluster %s".formatted(cluster));
        hazelcastInstanceClient.getPartitionService().addMigrationListener(clientMigrationListener);

        // all in microseconds, which we use as a standard
        final long statsReportFrequency = 10000;
        final long migrationsCheckFrequency = 5000;
        final long timeInChaosStarted = 70000;
        final int timeToWaitAfterLastMigration = 90000;

        int maxEntries = 1 << 13;
        if (rapidTestMode)
            maxEntries = maxEntries >> 4;

        IMap<Integer, String> map = hazelcastInstanceClient.getMap("map");

        var statsReportStopwatch = new Stopwatch(statsReportFrequency); // ms
        var migrationsCheckStopwatch = new Stopwatch(migrationsCheckFrequency); // ms

        enum TestStage {
            LOAD,
            GOTOCHAOSSTART,
            CHAOSSTARTED,
            GOTOCHAOSSTOP,
            CHAOSSTOPPED,
            REPORTED
        }

        TestStage testStage = TestStage.LOAD;
        String statsBeforeChaos = "";

        KeyBoundary keyBoundary = null;
        MyRunnables runnables = null;

        try (var threadPool = new ThreadPool()) {
            final long executorSubmitBackoff = 250; // ms

            while (true) {
                awaitConnected(clientStateListener);

                if (keyBoundary == null) {
                    keyBoundary = createMapAndGetLastKey(threadPool, clientStateListener, map, maxEntries);
                    runnables = new MyRunnables();
                    clientMigrationListener.setMigrationEndReportingSupplier(runnables);
                    runnables.add(new IsEmptyRunnable(map));
                    runnables.add(new PutIfAbsentRunnable(map, mapValueSize, keyBoundary.firstKey(), keyBoundary.lastKey()));
                }

                // Submit one of each type of operation
                for (Runnable runnable : runnables)
                    if (threadPool.submit(runnable))
                        statsReportStopwatch.addUnit();
                    else
                        Thread.sleep(executorSubmitBackoff);

                /* If there were any migrations previously reported, or we just
                 * observed a large timeout, check on the cluster health and see
                 * if we're running any migrations currently.
                 */
                if (migrationsCheckStopwatch.isTimeOver()) {
                    clientMembershipListener.logCurrentMembershipIfMissingMembers();
                    clientMigrationListener.logAnyActiveMigrations();
                }

                if (statsReportStopwatch.isTimeOver()) {
                    logger.log("OPSRATE -> %,.2f/s / STATS -> %s".formatted(statsReportStopwatch.ratePerSecond(),
                            runnables.listRunnablesToString()));

                    boolean weHaveEnoughData =
                            runnables.stream().allMatch(IMapMethodRunnable::hasReachedMinimumPopulation);
                    var chaosStartTime = socketResponseResponder.getChaosStartTime();

                    // See if we're ready to start testing
                    testStage = switch (testStage) {
                        case LOAD -> {
                            if (rapidTestMode || weHaveEnoughData) {
                                statsBeforeChaos = runnables.listRunnablesToCSV();
                                // Signal to client that we are ready to proceed
                                socketResponseResponder.setIsReadyForChaosStart();
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
                                runnables.forEach(IMapMethodRunnable::clearStats);
                                yield TestStage.CHAOSSTARTED;
                            } else {
                                yield testStage;
                            }
                        }
                        case CHAOSSTARTED -> {
                            if (rapidTestMode || millisBetween(chaosStartTime, Instant.now()) >= timeInChaosStarted) {
                                socketResponseResponder.setIsNotReadyForChaosStart();
                                socketResponseResponder.setIsReadyForChaosStop();
                                yield TestStage.GOTOCHAOSSTOP;
                            }
                            yield testStage;
                        }
                        case GOTOCHAOSSTOP -> {
                            if (socketResponseResponder.getIsChaosStopped()) {
                                socketResponseResponder.setIsNotReadyForChaosStop();
                                yield TestStage.CHAOSSTOPPED;
                            }
                            yield testStage;
                        }
                        case CHAOSSTOPPED -> {
                            var timeMigrationEnded = clientMigrationListener.getInstantEndOfLastMigration();
                            if (rapidTestMode || (timeMigrationEnded != null &&
                                    millisBetween(timeMigrationEnded, Instant.now()) >= timeToWaitAfterLastMigration &&
                                    !clientMigrationListener.isMigrationActive() &&
                                    !clientMembershipListener.clusterIsMissingMembers())) {
                                if (rapidTestMode) {
                                    logger.log("*** SENDING FAKE TEST RESULTS ***");
                                    socketResponseResponder.setTestResult("0,0,0,0"); // fake data
                                } else {
                                    logger.log("*** CLEARING LAST MIGRATION AND SENDING TEST RESULTS ***");
                                    socketResponseResponder.setTestResult(
                                            secondsBetween(chaosStartTime, timeMigrationEnded) + "," +
                                                    statsBeforeChaos + "," +
                                                    clientMigrationListener.getMigrationEndInfoSupplied());
                                    clientMigrationListener.clearLastMigration();
                                }
                                yield TestStage.REPORTED;
                            } else {
                                yield testStage;
                            }
                        }
                        case REPORTED -> {
                            if (socketResponseResponder.getIsTestResultReceived()) {
                                runnables.forEach(IMapMethodRunnable::clearStats);
                                socketResponseResponder.resetTest();
                                statsBeforeChaos = null;
                                keyBoundary = null; // Trigger a clear and reload of map!
                                yield TestStage.LOAD;
                            } else {
                                yield testStage;
                            }
                        }
                    };
                }
            }
        }
    }
}
