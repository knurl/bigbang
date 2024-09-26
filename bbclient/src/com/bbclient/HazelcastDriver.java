package com.bbclient;

import java.util.concurrent.*;

class HazelcastDriver extends Thread implements AutoCloseable {
    final Logger logger;
    final ExecutorService pool;
    final Main.RunnablesList runnablesList;
    final long statsFrequencyMillis;

    /*
     * Synchronized
     */
    boolean drain = false;

    public synchronized boolean isDraining() {
        return this.drain;
    }

    public synchronized void setDrain() {
        this.drain = true;
    }

    /*
     * Constructor and non-synchronized
     */

    public HazelcastDriver(String name,
                           Main.RunnablesList runnablesList,
                           long statsFrequencyMillis) {
        this.logger = new Logger(name);
        this.runnablesList = runnablesList;
        this.statsFrequencyMillis = statsFrequencyMillis;

        final int numThreads = Main.localTestMode ? 2 : 6;
        final int numThreadsMax = (Main.localTestMode ? 2 : 8) * numThreads;
        final int threadQueueSize = numThreadsMax * 2;
        int keepAliveTimeSec = 60; // seconds

        this.pool = new ThreadPoolExecutor(numThreads, numThreadsMax,
                keepAliveTimeSec, TimeUnit.SECONDS,
                new ArrayBlockingQueue<>(threadQueueSize),
                new ThreadPoolExecutor.AbortPolicy());
    }

    public void submit(Runnable runnable) {
        boolean submitted = false;
        var threadpoolSubmitBackoffMillis = 250; // ms
        while (!isDraining() && !submitted) {
            try {
                pool.submit(runnable);
                submitted = true;
            } catch (RejectedExecutionException e) {
                try {
                    Thread.sleep(threadpoolSubmitBackoffMillis);
                } catch (InterruptedException e2) {
                    logger.log("*** RECEIVED INTERRUPTED EXCEPTION [SUBMIT] *** %s".formatted(e2));
                    Thread.currentThread().interrupt();
                }
            }
        }
    }

    public void run() {
        logger.log("Starting up operations");
        var statsStopwatch = new Stopwatch(statsFrequencyMillis);

        while (!isDraining()) {
            for (Runnable runnable : runnablesList) {
                if (isDraining())
                    break;
                submit(runnable);
                if (!isDraining() && statsStopwatch.isTimeOver()) {
                    logger.log("STATS => " + runnablesList.listRunnablesToStatsString());
                }
            }
        }
    }

    public boolean reachedMinimumStatsPopulation() {
        return this.runnablesList.stream().allMatch(IMapMethodRunnable::hasReachedMinimumPopulation);
    }

    private void drain() throws InterruptedException {
        setDrain();
        pool.shutdown();
        if (!pool.awaitTermination(2, TimeUnit.SECONDS)) {
            logger.log("Timed out waiting for termination in drain()");
            pool.shutdownNow();
        }
    }

    public void drainAndJoin() {
        try {
            drain();
            this.join();
        } catch (InterruptedException e) {
            throw new RuntimeException(e);
        }
    }

    public String drainAndGetStats() {
        try {
            drain();
            return runnablesList.listRunnablesToCSV();
        } catch (InterruptedException e) {
            logger.log("*** RECEIVED EXCEPTION [GET] *** %s".formatted(e));
            throw new RuntimeException(e);
        }
    }

    public void close() {
        try {
            drain();
        } catch (InterruptedException e) {
            pool.shutdownNow();
            Thread.currentThread().interrupt();
        }
        pool.shutdownNow();

        for (var runnable: runnablesList) {
            runnable.close();
        }
    }
}
