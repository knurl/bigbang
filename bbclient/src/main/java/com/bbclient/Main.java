package com.bbclient;

import com.hazelcast.client.HazelcastClient;
import com.hazelcast.client.config.ClientConfig;
import com.hazelcast.client.util.ClientStateListener;
import com.hazelcast.core.HazelcastInstance;
import com.hazelcast.map.IMap;
import com.hazelcast.shaded.nonapi.io.github.classgraph.utils.StringUtils;

import java.net.MalformedURLException;
import java.net.URISyntaxException;
import java.rmi.ServerException;
import java.time.Duration;
import java.time.Instant;
import java.time.format.DateTimeFormatterBuilder;
import java.util.ArrayList;
import java.util.List;
import java.util.Random;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

import static com.bbclient.RandomStringBuilder.generateRandomString;

class Main {
    private final static String searchDomain = ".hazelcast.net";
    private final static String clusterName = "dev";
    private final static String clusterLoadBalancerName = clusterName + searchDomain;
    private final static String mapName = "map";

    static final int mapValueSizeMin = 1 << 12;
    static final int mapValueSizeMax = 1 << 26;

    static Random random = new Random();

    private final static long firstKey = random.nextLong();
    private static long nextKey = firstKey;
    private static long lastKey = nextKey;

    // How many entries do we want to inject into the map?
    static final long maxHeapCost = 16L*1024*1024*1024;

    // How often should we dump our collected statistics on response times?
    static final int statsReportFrequency = 60000; // ms

    // Keep track of the current and last batch size, and the last batch rate
    static int batchSize = 1;
    static int lastBatchSize = batchSize;
    static int lastBatchRate = -1;
    static final int batchSizeMax = 1 << 20;

    public static void setAsyncBatch(IMap<Long, String> map) throws Throwable {
        List<CompletableFuture<Void>> futureList = new ArrayList<>();

        Instant start = Instant.now();

        // Fire off a set of async set
        for (int i = 0; i < Main.batchSize; i++) {
            int mapValueSize = random.nextInt(mapValueSizeMin, mapValueSizeMax);
            futureList.add(map.setAsync(nextKey,
                    generateRandomString(mapValueSize)).toCompletableFuture());
            lastKey = nextKey;
            nextKey++;
        }
        try {
            futureList.forEach(CompletableFuture::join);
        } catch (CompletionException ex) {
            try {
                throw ex.getCause();
            } catch (Error | RuntimeException | ServerException possible) {
                throw possible;
            } catch (Throwable impossible) {
                throw new AssertionError(impossible);
            }
        }

        Instant finish = Instant.now();

        final long batchTime = Duration.between(start, finish).toMillis();

        // Protect from division by zero as we calculate the ops/s rate
        if (batchTime > 0) {
            final int batchRate = (int) (batchSize * 1_000 / batchTime); // convert to ops/s

            // Capture batch size before modifying it
            lastBatchSize = batchSize;

            // Ignore first loop, and protect against by div-by-0
            if (lastBatchRate > 0) {
                final double changeRatio = (double) (batchRate - lastBatchRate) / (double) lastBatchRate;
                final int change = (int) Math.round((double)batchSize * changeRatio);

                /* Add change to batch size, but don't allow batch size to
                 * more than double, or exceed batchSizeMax ever, and it
                 * always has to be at least 1.
                 */
                batchSize = Math.max(1,
                        Math.min(batchSizeMax,
                        Math.min(lastBatchSize << 1,
                                batchSize + change)));
            }

            // Now we no longer need last batch rate, we can reassign
            lastBatchRate = batchRate;
        }
    }

    static String now(String s) {
        var formatter = new DateTimeFormatterBuilder().appendInstant(3).toFormatter();
        return "%s: %s".formatted(formatter.format(Instant.now()), s);
    }

    static void loadLog(String s) {
        var prefixElements = new ArrayList<String>();
        prefixElements.add("LOADING");
        if (lastBatchSize >= 0)
            prefixElements.add("BSZ=%,d".formatted(lastBatchSize));
        if (lastBatchRate >= 0)
            prefixElements.add("O/s=%,d".formatted(lastBatchRate));
        String prefixString = "[%s] -> ".formatted(StringUtils.join(" ", prefixElements));
        System.out.println(now("%s%s".formatted(prefixString, s)));
    }

    static void log(String s) {
        System.out.println(now(s));
    }

    static void awaitConnected(ClientStateListener listener) {
        var backoff = 10; // ms

        while (true) {
            try {
                listener.awaitConnected();
                return;
            } catch (InterruptedException ex) {
                loadLog("*** RECEIVED EXCEPTION [AWAITCONN] *** %s"
                        .formatted(ex.getClass().getSimpleName()));
                backoff <<= 1;

                try {
                    Thread.sleep(backoff);
                } catch (InterruptedException ex2) {
                    loadLog(("*** RECEIVED EXCEPTION [SLEEPING] *** %s")
                            .formatted(ex2.getClass().getSimpleName()));
                    backoff <<= 1;
                }
            }
        }
    }

    private static void clearMap(ManCtrThread manCtrThread,
                                 ClientStateListener listener,
                                 IMap<Long, String> map) throws InterruptedException {
        final long stopwatchTimeout = 2_500; // ms

        loadLog("TARGET HWM HEAP COST -> " + bytesToGigabytes(maxHeapCost));

        while (true) {
            awaitConnected(listener);

            loadLog("Clearing map");
            map.clear();
            /*
             * The map.clear() won't take effect with Management Center
             * immediately, so we'll have to wait until it catches up.
             */
            Thread.sleep(stopwatchTimeout);

            var heapCost = manCtrThread.getHeapCost();
            if (0 <= heapCost && heapCost < maxHeapCost >> 2)
                break;
        }
    }

    private static String bytesToGigabytes(long bytes) {
        return "%,.2f GB".formatted((double)bytes / Math.pow(1024.0, 3));
    }

    private static void fillMap(ManCtrThread manCtrThread,
                                ClientStateListener listener,
                                IMap<Long, String> map) {
        final long stopwatchTimeout = 1_000; // ms
        var fullnessCheckStopwatch = new Stopwatch(stopwatchTimeout); // ms
        var lastHeapCost = manCtrThread.getHeapCost();

        while (lastHeapCost < maxHeapCost) {
            awaitConnected(listener);

            if (fullnessCheckStopwatch.isTimeOver())
                lastHeapCost = manCtrThread.getHeapCost();

            assert(lastHeapCost >= 0);

            loadLog("Map size -> %s".formatted(bytesToGigabytes(lastHeapCost)));

            try { // Fire off a batch of parallel async set() operations
                setAsyncBatch(map);
            } catch (Throwable ex) {
                loadLog("*** RECEIVED EXCEPTION [LOADING] *** %s".formatted(ex.getClass().getSimpleName()));
            }
        }

        loadLog("+++ Filling complete -> %s +++".formatted(bytesToGigabytes(lastHeapCost)));
    }

    public static void main(String[] args) throws InterruptedException, MalformedURLException, URISyntaxException {
        ClientConfig clientConfig = new ClientConfig();
        /* This should connect to the dev service, which is a load balancer
           service used for client discovery created by the Operator */
        var clientNetworkConfig = clientConfig.getNetworkConfig();
        clientNetworkConfig.addAddress(clusterLoadBalancerName);
        clientNetworkConfig.setSmartRouting(true);
        ClientStateListener clientStateListener = new ClientStateListener(clientConfig);
        HazelcastInstance hazelcastInstanceClient = HazelcastClient.newHazelcastClient(clientConfig);

        IMap<Long, String> map = hazelcastInstanceClient.getMap(mapName);

        /*
         * Connect to Management Center before we do anything else. This
         * command will block until it completes successfully in accessing
         * the Management Center REST interface.
         */
        var manCtrThread = new ManCtrThread(searchDomain, clusterName, mapName);
        loadLog("Starting Management Center Thread");
        manCtrThread.start();

        loadLog("Clearing map");
        clearMap(manCtrThread, clientStateListener, map);
        loadLog("Filling map");
        fillMap(manCtrThread, clientStateListener, map);

        var runnables = new ArrayList<Runnable>();
        var isEmptyRunnable = new IsEmptyRunnable(map);
        runnables.add(isEmptyRunnable);
        var putIfAbsentRunnable = new PutIfAbsentRunnable(map, mapValueSizeMin,
                mapValueSizeMax, firstKey, lastKey);
        runnables.add(putIfAbsentRunnable);

        var statsReportStopwatch = new Stopwatch(statsReportFrequency); // ms

        while (true) {
            awaitConnected(clientStateListener);

            runnables.forEach(Runnable::run);

            if (statsReportStopwatch.isTimeOver())
                runnables.forEach(x -> log(x.toString()));
        }
    }
}
