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
        return this.isMigrationActive;
    }

    private synchronized MigrationProgress getIsMigrationActive() {
        if (this.isMigrationActive) {
            assert this.migrationProgress != null;
            return this.migrationProgress;
        } else {
            assert this.migrationProgress == null;
            return null;
        }
    }

    // synchronized inside method
    /**
     * @param numPlanned Sets the new number of planned migrations
     * @param numCompleted Sets the new number of completed migrations
     * @throws IllegalArgumentException If MigrationState is not valid
     */
    private synchronized void setMigrationActive(int numPlanned, int numCompleted) {
        if (numPlanned < numCompleted)
            throw new IllegalArgumentException("setMigrationActive: planned %d < completed %d"
                    .formatted(numPlanned, numCompleted));

        this.migrationProgress = new MigrationProgress(numPlanned, numCompleted);
        this.isMigrationActive = true;
    }

    private synchronized void setMigrationFinished() {
        this.isMigrationActive = false;
        this.migrationProgress = null;
        this.instantEndOfLastMigration = Instant.now();
    }

    public synchronized Instant getInstantEndOfLastMigration() {
        return this.instantEndOfLastMigration;
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
