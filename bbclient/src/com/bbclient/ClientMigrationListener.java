package com.bbclient;

import com.hazelcast.partition.MigrationListener;
import com.hazelcast.partition.MigrationState;
import com.hazelcast.partition.ReplicaMigrationEvent;
import org.jetbrains.annotations.NotNull;

import java.time.Instant;

public class ClientMigrationListener implements MigrationListener {
    private final Logger logger = new Logger("Migrating");
    private record MigrationProgress(int numPlanned, int numCompleted) {}

    /*
     * Synchronized
     */
    private boolean isMigrationActive = false;
    private MigrationProgress migrationProgress = null;
    private Instant instantEndOfLastMigration = null;

    public synchronized boolean isMigrationActive() {
        return isMigrationActive;
    }

    public synchronized void clearLastMigration() {
        isMigrationActive = false;
        migrationProgress = null;
        instantEndOfLastMigration = null;
    }

    private synchronized MigrationProgress getIsMigrationActive() {
        if (isMigrationActive) {
            assert migrationProgress != null;
            return migrationProgress;
        } else {
            assert migrationProgress == null;
            return null;
        }
    }

    /**
     * @param numPlanned Sets the new number of planned migrations
     * @param numCompleted Sets the new number of completed migrations
     * @throws IllegalArgumentException If MigrationState is not valid
     */
    private synchronized void setMigrationActive(int numPlanned, int numCompleted) {
        if (numPlanned < numCompleted)
            throw new IllegalArgumentException("setMigrationActive: planned %d < completed %d"
                    .formatted(numPlanned, numCompleted));

        migrationProgress = new MigrationProgress(numPlanned, numCompleted);
        isMigrationActive = true;
        instantEndOfLastMigration = null;
    }

    private synchronized void setMigrationFinished() {
        isMigrationActive = false;
        migrationProgress = null;
        instantEndOfLastMigration = Instant.now();
        logger.log("End of last migration=%s".formatted(instantEndOfLastMigration));
    }

    public void setMigrationFinishedAfterDelay(int timeout) {
        try {
            Thread.sleep(timeout);
        } catch (InterruptedException e) {
            logger.log("*** RECEIVED INTERRUPTED EXCEPTION [SETMIGRFINDEL] *** %s".formatted(e));
            Thread.currentThread().interrupt();
        }

        setMigrationFinished();
    }

    public synchronized Instant getInstantEndOfLastMigration() {
        return instantEndOfLastMigration;
    }

    /*
     * Constructor and other non-synchronized methods
     */

    public ClientMigrationListener() {
        logger.log("Initializing new %s()".formatted(this.getClass().getSimpleName()));
    }

    public void logAnyActiveMigrations() {
        var migrationProgress= getIsMigrationActive();
        if (migrationProgress != null) {
            var r = String.format("%d/%d migrations complete",
                    migrationProgress.numCompleted,
                    migrationProgress.numPlanned);
            logger.log(r);
        }
    }

    /*
     * Methods called by listeners
     */

    @Override
    public void migrationStarted(MigrationState migrationState) {
        setMigrationActive(migrationState.getPlannedMigrations(), migrationState.getCompletedMigrations());
        logger.log("Started");
        logAnyActiveMigrations();
    }

    @Override
    public void migrationFinished(MigrationState migrationState) {
        logAnyActiveMigrations();
        logger.log("Finished");
        setMigrationFinished();
    }

    @Override
    public void replicaMigrationCompleted(@org.jetbrains.annotations.NotNull ReplicaMigrationEvent replicaMigrationEvent) {
        var migrationState = replicaMigrationEvent.getMigrationState();
        setMigrationActive(migrationState.getPlannedMigrations(), migrationState.getCompletedMigrations());
    }

    @Override
    public void replicaMigrationFailed(@NotNull ReplicaMigrationEvent replicaMigrationEvent) {
        var migrationState = replicaMigrationEvent.getMigrationState();
        setMigrationActive(migrationState.getPlannedMigrations(), migrationState.getCompletedMigrations());
    }
}
