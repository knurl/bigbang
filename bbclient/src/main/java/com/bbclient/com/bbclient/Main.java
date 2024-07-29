package com.bbclient;

import com.hazelcast.client.HazelcastClient;
import com.hazelcast.client.config.ClientConfig;
import com.hazelcast.client.util.ClientStateListener;
import com.hazelcast.core.HazelcastInstance;
import com.hazelcast.map.IMap;
import org.jetbrains.annotations.NotNull;

import java.net.MalformedURLException;
import java.net.URISyntaxException;
import java.time.Duration;
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
            new ThreadPoolExecutor.CallerRunsPolicy());

    private final static String searchDomain = ".hazelcast.net";
    private final static String clusterName = "dev";
    private final static String clusterLoadBalancerName = clusterName + searchDomain;
    private final static String mapName = "map";

    static final int mapValueSize = 1 << 20;

    private final static long firstKey = (new Random()).nextLong();

    // How many entries do we want to inject into the map?
    static final long maxHeapCost = 10L*1024*1024*1024;

    static void awaitConnected(ClientStateListener listener) {
        var backoff = 10; // ms

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

    private static void clearMap(ManCtrThread manCtrThread,
                                 ClientStateListener listener,
                                 IMap<Long, String> map) {
        final long stopwatchTimeout = 1_000; // ms

        log("Clearing map");

        while (true) {
            awaitConnected(listener);

            map.clear();
            /*
             * The map.clear() won't take effect with Management Center
             * immediately, so we'll have to wait until it catches up.
             */
            try {
                Thread.sleep(stopwatchTimeout);
            } catch (InterruptedException e) {
                throw new RuntimeException(e);
            }

            long heapCost;
            try {
                heapCost = manCtrThread.getHeapCost();
            } catch (NotReadyException e) {
                try {
                    Thread.sleep(stopwatchTimeout);
                } catch (InterruptedException ex) {
                    throw new RuntimeException(ex);
                }
                continue;
            }
            if (0 <= heapCost && heapCost < maxHeapCost >> 2)
                break;
        }

        log("Map is cleared");
    }

    private static @NotNull String bytesToGigabytes(long bytes) {
        return "%,.2f GB".formatted((double)bytes / Math.pow(1024.0, 3));
    }

    private static long fillMapAndGetLastKey(ManCtrThread manCtrThread,
                                             ClientStateListener listener,
                                             IMap<Long, String> map) {
        final long stopwatchTimeout = 1_000; // ms
        var fullnessCheckStopwatch = new Stopwatch(stopwatchTimeout); // ms
        long lastHeapCost = 0;

        log("TARGET HWM HEAP COST -> " + bytesToGigabytes(maxHeapCost));

        SetRunnable setRunnable = new SetRunnable(map, mapValueSize, firstKey);
        while (lastHeapCost < maxHeapCost) {
            awaitConnected(listener);

            if (fullnessCheckStopwatch.isTimeOver()) {
                try {
                    lastHeapCost = manCtrThread.getHeapCost();
                } catch (NotReadyException e) {
                    try {
                        Thread.sleep(stopwatchTimeout);
                    } catch (InterruptedException ex) {
                        throw new RuntimeException(ex);
                    }
                }
                log("Map size -> %s".formatted(bytesToGigabytes(lastHeapCost)));
            }

            executorService.submit(setRunnable);
        }

        log("+++ Filling complete -> %s +++".formatted(bytesToGigabytes(lastHeapCost)));
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

        if (!isClusterSafe && wasClusterSafe) {
                log(logPrefix + "Cluster is no longer safe!");
                log(logPrefix + "QLEN=%d NMEM=%d".formatted(
                        migrationQ,
                        numMembers));
        } else if (isClusterSafe && !wasClusterSafe) {
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

    public static void main(String[] args) throws MalformedURLException, URISyntaxException, InterruptedException {
        ClientConfig clientConfig = new ClientConfig();
        /* This should connect to the dev service, which is a load balancer
           service used for client discovery created by the Operator */
        var clientNetworkConfig = clientConfig.getNetworkConfig();
        clientNetworkConfig.addAddress(clusterLoadBalancerName);
        clientNetworkConfig.setSmartRouting(true);
        ClientStateListener clientStateListener = new ClientStateListener(clientConfig);
        HazelcastInstance hazelcastInstanceClient = HazelcastClient.newHazelcastClient(clientConfig);
        final int statsReportFrequency = 60000; // ms
        final int backoffTimeoutMillis = 1000; // ms

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

        clearMap(manCtrThread, clientStateListener, map);
        final var lastKey = fillMapAndGetLastKey(manCtrThread,
                clientStateListener, map);

        var runnables = new ArrayList<IMapMethodRunnable>();
        var isEmptyRunnable = new IsEmptyRunnable(map);
        runnables.add(isEmptyRunnable);
        var putIfAbsentRunnable = new PutIfAbsentRunnable(map, mapValueSize,
                firstKey, lastKey);
        runnables.add(putIfAbsentRunnable);

        var statsReportStopwatch = new Stopwatch(statsReportFrequency); // ms
        boolean isClusterSafe = true;

        while (true) {
            awaitConnected(clientStateListener);

            for (Runnable runnable : runnables)
                executorService.submit(runnable);

            if (statsReportStopwatch.isTimeOver())
                runnables.forEach(x -> log(x.toString()));

            /* If there were any migrations previously reported, or we just
             * observed a large timeout, check on the cluster health and see
             * if we're running any migrations currently.
             */
            try {
                isClusterSafe = reportAnyMigrations(manCtrThread, isClusterSafe);
            } catch (NotReadyException e) {
                Thread.sleep(backoffTimeoutMillis);
            }
        }
    }
}
