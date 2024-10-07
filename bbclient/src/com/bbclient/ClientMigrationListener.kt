package com.bbclient

import com.hazelcast.partition.MigrationListener
import com.hazelcast.partition.MigrationState
import com.hazelcast.partition.ReplicaMigrationEvent
import java.time.Instant

class ClientMigrationListener : MigrationListener {
    private val logger = Logger("Migrating")

    @JvmRecord
    private data class MigrationProgress(val numPlanned: Int, val numCompleted: Int)

    /*
    * Synchronized
    */
    @get:Synchronized
    var isMigrationActive: Boolean = false
        private set
    private var migrationProgress: MigrationProgress? = null

    @get:Synchronized
    var instantEndOfLastMigration: Instant? = null
        private set

    @Synchronized
    fun clearLastMigration() {
        isMigrationActive = false
        migrationProgress = null
        instantEndOfLastMigration = null
    }

    @Synchronized
    private fun getIsMigrationActive(): MigrationProgress? {
        if (isMigrationActive) {
            checkNotNull(migrationProgress)
            return migrationProgress
        } else {
            assert(migrationProgress == null)
            return null
        }
    }

    /**
     * @param numPlanned Sets the new number of planned migrations
     * @param numCompleted Sets the new number of completed migrations
     * @throws IllegalArgumentException If MigrationState is not valid
     */
    @Synchronized
    private fun setMigrationActive(numPlanned: Int, numCompleted: Int) {
        require(numPlanned >= numCompleted) {
            "setMigrationActive: planned %d < completed %d".format(numPlanned, numCompleted)
        }

        migrationProgress = MigrationProgress(numPlanned, numCompleted)
        isMigrationActive = true
        instantEndOfLastMigration = null
    }

    @Synchronized
    fun setMigrationFinished() {
        isMigrationActive = false
        migrationProgress = null
        instantEndOfLastMigration = Instant.now()
        logger.log("End of last migration=%s".format(instantEndOfLastMigration))
    }

    /*
     * Constructor and other non-synchronized methods
     */
    init {
        logger.log("Initializing new %s()".format(javaClass.simpleName))
    }

    fun logAnyActiveMigrations() {
        val migrationProgress = getIsMigrationActive()
        if (migrationProgress != null) {
            val r = String.format(
                "%d/%d migrations complete",
                migrationProgress.numCompleted,
                migrationProgress.numPlanned
            )
            logger.log(r)
        }
    }

    /*
     * Methods called by listeners
     */
    override fun migrationStarted(migrationState: MigrationState) {
        setMigrationActive(migrationState.plannedMigrations, migrationState.completedMigrations)
        logger.log("Started")
        logAnyActiveMigrations()
    }

    override fun migrationFinished(migrationState: MigrationState) {
        logAnyActiveMigrations()
        logger.log("Finished")
        setMigrationFinished()
    }

    override fun replicaMigrationCompleted(replicaMigrationEvent: ReplicaMigrationEvent) {
        val migrationState = replicaMigrationEvent.migrationState
        setMigrationActive(migrationState.plannedMigrations, migrationState.completedMigrations)
    }

    override fun replicaMigrationFailed(replicaMigrationEvent: ReplicaMigrationEvent) {
        val migrationState = replicaMigrationEvent.migrationState
        setMigrationActive(migrationState.plannedMigrations, migrationState.completedMigrations)
    }
}
