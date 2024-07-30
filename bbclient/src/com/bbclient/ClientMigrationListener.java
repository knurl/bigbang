package com.bbclient;

import com.hazelcast.partition.MigrationListener;
import com.hazelcast.partition.MigrationState;
import com.hazelcast.partition.ReplicaMigrationEvent;

import static com.bbclient.Logger.log;

public class ClientMigrationListener implements MigrationListener {
    @Override
    public void migrationFinished(MigrationState migrationState) {
        log("migrationFinished() -> %s".formatted(migrationState));
    }

    @Override
    public void migrationStarted(MigrationState migrationState) {
        log("migrationStarted() -> %s".formatted(migrationState));
    }

    @Override
    public void replicaMigrationCompleted(ReplicaMigrationEvent replicaMigrationEvent) {
        log("replicaMigrationCompleted() -> %s".formatted(replicaMigrationEvent));
        log("replicaMigrationState() (on completion) -> %s"
                .formatted(replicaMigrationEvent.getMigrationState()));
    }

    @Override
    public void replicaMigrationFailed(ReplicaMigrationEvent replicaMigrationEvent) {
        log("replicaMigrationFailed() -> %s".formatted(replicaMigrationEvent));
        log("replicaMigrationState() (on failed) -> %s"
                .formatted(replicaMigrationEvent.getMigrationState()));
    }

}
