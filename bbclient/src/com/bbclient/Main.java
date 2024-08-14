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
import java.util.Random;
import java.util.concurrent.*;

class Main {
    static final int portNumber = 4000;

    static final int numThreads = 6;
    static final int numThreadsMax = 2*numThreads;
    static final int threadQueueSize = 4*numThreads;
    static final int keepAliveTimeSec = 60; // seconds

    private final static String mapName = "map";

    static final int mapValueSize = 1 << 20;
//    static final int maxEntries = 1000*4;
    static final int maxEntries = 1000;
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

    record KeyBoundary(long firstKey, long lastKey) {}

    private static KeyBoundary createMapAndGetLastKey(ClientStateListener listener,
                                                      IMap<Long, String> map) throws InterruptedException {
        long createMapPauseMillis = 3_000;
        double opsRateAverage = 0.0;
        KeyBoundary keyBoundary = null;

        while (opsRateAverage < 100.0) {
            if (opsRateAverage > 0.0) {
                logger.log("OpsRateAverage = %,f too low; Trying again".formatted(opsRateAverage));
                Thread.sleep(createMapPauseMillis);
            }

            logger.log("Clearing map");
            awaitConnected(listener);
            map.clear();
            logger.log("Map is cleared");

            DescriptiveStatistics opsRateStats = new DescriptiveStatistics();

            logger.log("+++ TARGET MAP SIZE -> %,d +++".formatted(maxEntries));

            var random = new Random();
            final var firstKey = random.nextLong(Long.MIN_VALUE, Long.MAX_VALUE >> 1);
            SetRunnable setRunnable = new SetRunnable(map, mapValueSize, firstKey);

            long mapSize = 0;

            try (var threadPool = new ThreadPool()) {
                final long executorSubmitBackoff = 250; // ms
                final long fullnessCheckTimeout = 2_000; // ms
                var fullnessCheckStopwatch = new Stopwatch(fullnessCheckTimeout); // ms

                while (mapSize < maxEntries) {
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
            }

            logger.log("+++ ACTUAL MAP SIZE -> %,d +++".formatted(mapSize));
            opsRateAverage = opsRateStats.getMean();
            keyBoundary = new KeyBoundary(firstKey, setRunnable.getLastKey());
        }

        return keyBoundary;
    }

    public static String listRunnablesToString(List<IMapMethodRunnable> runnables) {
        List<String> statsSummaries = new ArrayList<>();
        runnables.forEach(x -> statsSummaries.add(x.toString()));
        return String.join("; ", statsSummaries);
    }

    public static String listRunnablesToCSV(List<IMapMethodRunnable> runnables) {
        List<String> statsCSVs = new ArrayList<>();
        runnables.forEach(x -> statsCSVs.add(x.toCSV()));
        return String.join(",", statsCSVs);
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

        final long statsReportFrequency = 30000; // ms
        final long migrationsCheckFrequency = 10000; // ms
        final int secondsToWaitAfterLastMigration = 60; // sec

        IMap<Long, String> map = hazelcastInstanceClient.getMap(mapName);

        var keyBoundary= createMapAndGetLastKey(clientStateListener, map);

        var runnables = new ArrayList<IMapMethodRunnable>();
        var isEmptyRunnable = new IsEmptyRunnable(map);
        runnables.add(isEmptyRunnable);
        var putIfAbsentRunnable = new PutIfAbsentRunnable(map, mapValueSize,
                keyBoundary.firstKey(), keyBoundary.lastKey());
        runnables.add(putIfAbsentRunnable);

        var statsReportStopwatch = new Stopwatch(statsReportFrequency); // ms
        var migrationsCheckStopwatch = new Stopwatch(migrationsCheckFrequency); // ms
        boolean setIsReadyForTesting = false;
        Instant timeMigrationEnded;

        try (var threadPool = new ThreadPool()) {
            final long executorSubmitBackoff = 250; // ms

            while (true) {
                awaitConnected(clientStateListener);

                for (Runnable runnable : runnables)
                    if (threadPool.submit(runnable))
                        statsReportStopwatch.addUnit();
                    else
                        Thread.sleep(executorSubmitBackoff);

                if (statsReportStopwatch.isTimeOver()) {
                    var opsRate = statsReportStopwatch.ratePerSecond();
                    logger.log("OPSRATE -> %,.2f/s / STATS -> %s".formatted(opsRate, listRunnablesToString(runnables)));

                    // See if we're ready to start testing
                    if (!setIsReadyForTesting && opsRate >= 100.0 &&
                            runnables.stream().allMatch(IMapMethodRunnable::hasReachedMinimumPopulation)) {
                        logger.log("We are ready for chaos testing to start");
                        socketResponseResponder.setIsReadyForTesting();
                        setIsReadyForTesting = true;
                    }

                    // See if we're done testing
                    if ((timeMigrationEnded = clientMigrationListener.getInstantEndOfLastMigration()) != null) {
                        if (!clientMigrationListener.isMigrationActive() &&
                                Duration.between(timeMigrationEnded, Instant.now()).toSeconds() >=
                                secondsToWaitAfterLastMigration) {
                            var fullTestLength = Duration.between(socketResponseResponder.getChaosStartTime(),
                                    timeMigrationEnded).toSeconds();
                            var testResults = new StringBuilder();
                            testResults.append(fullTestLength);
                            testResults.append(",");
                            testResults.append(listRunnablesToCSV(runnables));
                            logger.log("TESTRESULTS: " + testResults);
                            socketResponseResponder.setIsTestingComplete(testResults.toString());
                        }
                    }
                }

                /* If there were any migrations previously reported, or we just
                 * observed a large timeout, check on the cluster health and see
                 * if we're running any migrations currently.
                 */
                if (migrationsCheckStopwatch.isTimeOver()) {
                    clientMembershipListener.logCurrentMembershipIfMissingMembers();
                    clientMigrationListener.logAnyActiveMigrations();
                }
            }
        }
    }
}
