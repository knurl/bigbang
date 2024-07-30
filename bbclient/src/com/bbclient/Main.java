package com.bbclient;

import com.hazelcast.client.HazelcastClient;
import com.hazelcast.client.config.ClientConfig;
import com.hazelcast.client.util.ClientStateListener;
import com.hazelcast.core.Hazelcast;
import com.hazelcast.core.HazelcastInstance;
import com.hazelcast.map.IMap;

import java.net.MalformedURLException;
import java.net.URISyntaxException;
import java.util.ArrayList;
import java.util.Random;
import java.util.concurrent.*;

import static com.bbclient.Logger.log;

class Main {
    static final int numThreads = 3;
    static final ExecutorService executorService = new ThreadPoolExecutor(
            numThreads, numThreads*2, 60,
            TimeUnit.SECONDS,
            new ArrayBlockingQueue<>(numThreads*6),
            new ThreadPoolExecutor.AbortPolicy());
    static final long executorSubmitBackoff = 250; // ms

    private final static String searchDomain = ".hazelcast.net";
    private final static String clusterName = "dev";
    private final static String clusterLoadBalancerName = clusterName + searchDomain;
    private final static String mapName = "map";

    static final int mapValueSize = 1 << 20;

    private final static long firstKey = (new Random()).nextLong();

    // How big a heap cost should the map reach when filling the first time?
    static final long heapLowWaterMark = 10L*1024*1024*1024;
    // What's the biggest the map can be before we clear it?
    static final long heapHighWaterMark = heapLowWaterMark + (heapLowWaterMark >> 3);

    private static String bytesToGigabytes(long bytes) {
        return "%,.2f GB".formatted((double)bytes / Math.pow(1024.0, 3));
    }

    static void awaitConnected(ClientStateListener listener) {
        var backoff = 50; // ms

        while (true) {
            try {
                listener.awaitConnected();
                return;
            } catch (InterruptedException ex) {
                log("*** RECEIVED EXCEPTION [AWAITCONN] *** %s"
                        .formatted(ex.getClass().getSimpleName()));
                backoff <<= 1;

                try {
                    Thread.sleep(backoff);
                } catch (InterruptedException ex2) {
                    log(("*** RECEIVED EXCEPTION [SLEEPING] *** %s")
                            .formatted(ex2.getClass().getSimpleName()));
                    backoff <<= 1;
                }
            }
        }
    }

    static long getHeapCost(ManCtrThread manCtrThread,
                            ClientStateListener listener) {
        long heapCost = -1;
        final long backoffMillis = 250;

        while (heapCost < 0) {
            awaitConnected(listener);

            try {
                heapCost = manCtrThread.getHeapCost();
            } catch (NotReadyException ex) {
                try {
                    Thread.sleep(backoffMillis);
                } catch (InterruptedException ex2) {
                    log(("*** RECEIVED EXCEPTION [GETHEAPCOST] *** %s")
                            .formatted(ex2.getClass().getSimpleName()));
                }
            }
        }

        return heapCost;
    }

    private static void clearMapIfTooBig(ManCtrThread manCtrThread,
                                         ClientStateListener listener,
                                         IMap<Long, String> map) {
        long heapCost = getHeapCost(manCtrThread, listener);

        if (heapCost < heapHighWaterMark)
            return;
        else
            log("Heap cost = %s > HWM = %s. Clearing it.".formatted(bytesToGigabytes(heapCost),
                    bytesToGigabytes(heapHighWaterMark)));

        map.clear();

        final long pauseTimeout = 1_000; // ms

        /*
         * The map.clear() won't take effect with Management Center
         * immediately, so we'll have to wait until it catches up.
         */

        while (heapCost >= heapLowWaterMark >> 2) {
            heapCost = getHeapCost(manCtrThread, listener);

            try {
                Thread.sleep(pauseTimeout);
            } catch (InterruptedException ex) {
                log(("*** RECEIVED EXCEPTION [MAPCLEAR] *** %s")
                        .formatted(ex.getClass().getSimpleName()));
            }
        }

        log("Map is cleared");
    }

    private static long fillMapAndGetLastKey(ManCtrThread manCtrThread,
                                             ClientStateListener listener,
                                             IMap<Long, String> map) throws InterruptedException {
        final long stopwatchTimeout = 2_000; // ms
        var fullnessCheckStopwatch = new Stopwatch(stopwatchTimeout); // ms

        log("TARGET HWM HEAP COST -> " + bytesToGigabytes(heapLowWaterMark));

        SetRunnable setRunnable = new SetRunnable(map, mapValueSize, firstKey);

        long heapCost = -1;

        while (heapCost < heapLowWaterMark) {
            if (heapCost == -1 || fullnessCheckStopwatch.isTimeOver()) {
                heapCost = getHeapCost(manCtrThread, listener);
                log("Map size -> %s".formatted(bytesToGigabytes(heapCost)));
                continue;
            }

            try {
                executorService.submit(setRunnable);
            } catch (RejectedExecutionException ex) {
                Thread.sleep(executorSubmitBackoff);
            }
        }

        log("+++ Filling complete -> %s +++".formatted(bytesToGigabytes(heapCost)));
        return setRunnable.getLastKey();
    }

    static boolean reportAnyMigrations(ManCtrThread manCtrThread,
                                       boolean wasClusterSafe) throws NotReadyException {
        boolean isClusterSafe;
        int migrationQ;
        int numMembers;
        String logPrefix = "[MIGRATIONS] ";

        isClusterSafe = manCtrThread.getIsClusterSafe();
        migrationQ = manCtrThread.getPartitionMigrationQ();
        numMembers = manCtrThread.getNumMembers();

        if (!isClusterSafe) {
            if (wasClusterSafe)
                log(logPrefix + "Cluster is no longer safe!");

            log(logPrefix + "QLEN=%d NMEM=%d".formatted(
                    migrationQ,
                    numMembers));
        } else { // Cluster is safe
            if (!wasClusterSafe)
                log(logPrefix + "Cluster returned to safety");
        }

        return isClusterSafe;
    }

    static void waitUntilClusterSafe(ManCtrThread manCtrThread) throws InterruptedException {
        boolean isClusterSafe = true;
        log("Ensuring cluster is safe");

        do {
            try {
                isClusterSafe = reportAnyMigrations(manCtrThread, isClusterSafe);
            } catch (NotReadyException e) {
                Thread.sleep(1000);
                continue;
            }
            Thread.sleep(1000);
        } while (!isClusterSafe);

        log("Cluster is safe");
    }

    private static void registerEventListeners(HazelcastInstance hazelcastInstanceClient) {
        var cluster = hazelcastInstanceClient.getCluster();
        log("Registering ClientMembershipListener with cluster %s".formatted(cluster));
        cluster.addMembershipListener(new ClientMembershipListener());

        var memberInstances = Hazelcast.getAllHazelcastInstances();
        for (HazelcastInstance hazelcastInstanceMember: memberInstances) {
            log("Registering ClientMigrationListener with member %s".formatted(hazelcastInstanceMember));
            var partitionService = hazelcastInstanceMember.getPartitionService();
            partitionService.addMigrationListener(new ClientMigrationListener());
        }
    }

    public static void main(String[] args) throws MalformedURLException, URISyntaxException, InterruptedException {
        ClientConfig clientConfig = new ClientConfig();

        /* This should connect to the dev service, which is a load balancer
           service used for client discovery created by the Operator */
        var clientNetworkConfig = clientConfig.getNetworkConfig();
        clientNetworkConfig.addAddress(clusterLoadBalancerName);
        clientNetworkConfig.setSmartRouting(true);
        ClientStateListener clientStateListener = new ClientStateListener(clientConfig);
        HazelcastInstance hazelcastInstanceClient = HazelcastClient.newHazelcastClient(clientConfig);

        registerEventListeners(hazelcastInstanceClient);

        final long statsReportFrequency = 30000; // ms
        final long migrationsCheckFrequency = 5000; // ms
        final long backoffTimeoutMillis = 2000; // ms

        IMap<Long, String> map = hazelcastInstanceClient.getMap(mapName);

        /*
         * Connect to Management Center before we do anything else. This
         * command will block until it completes successfully in accessing
         * the Management Center REST interface.
         */
        var manCtrThread = new ManCtrThread(searchDomain, clusterName, mapName);
        log("Starting Management Center Thread");
        manCtrThread.start();

        waitUntilClusterSafe(manCtrThread);

        clearMapIfTooBig(manCtrThread, clientStateListener, map);
        final var lastKey = fillMapAndGetLastKey(manCtrThread,
                clientStateListener, map);

        var runnables = new ArrayList<IMapMethodRunnable>();
        var isEmptyRunnable = new IsEmptyRunnable(map);
        runnables.add(isEmptyRunnable);
        var putIfAbsentRunnable = new PutIfAbsentRunnable(map, mapValueSize,
                firstKey, lastKey);
        runnables.add(putIfAbsentRunnable);

        var statsReportStopwatch = new Stopwatch(statsReportFrequency); // ms
        var migrationsCheckStopwatch = new Stopwatch(migrationsCheckFrequency); // ms
        boolean isClusterSafe = true;

        while (true) {
            awaitConnected(clientStateListener);

            try {
                for (Runnable runnable : runnables)
                    executorService.submit(runnable);
            } catch (RejectedExecutionException ex) {
                Thread.sleep(executorSubmitBackoff);
            }

            if (statsReportStopwatch.isTimeOver())
                runnables.forEach(x -> log(x.toString()));

            /* If there were any migrations previously reported, or we just
             * observed a large timeout, check on the cluster health and see
             * if we're running any migrations currently.
             */
            if (migrationsCheckStopwatch.isTimeOver()) {
                try {
                    isClusterSafe = reportAnyMigrations(manCtrThread, isClusterSafe);
                } catch (NotReadyException ex) {
                    log("*** RECEIVED EXCEPTION [MIGRCHK] *** %s"
                            .formatted(ex.getClass().getSimpleName()));
                    Thread.sleep(backoffTimeoutMillis);
                }
            }
        }
    }
}
