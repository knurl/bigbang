package com.bbclient

import com.hazelcast.cluster.MembershipEvent
import com.hazelcast.cluster.MembershipListener

class ClientMembershipListener(originalNumMembers: Int) : MembershipListener {
    var logger: Logger = Logger("Membership")

    /*
     * Synchronized
     */
    private var originalNumMembers = 0
    private var currentNumMembers = 0

    init {
        logger.log(
            "Initializing new %s() with %d members".formatted(
                javaClass.simpleName,
                originalNumMembers
            )
        )
        synchronized(this) {
            this.originalNumMembers = originalNumMembers
            this.currentNumMembers = this.originalNumMembers
        }
    }

    @Synchronized
    fun clusterIsMissingMembers(): Boolean {
        return currentNumMembers < originalNumMembers
    }

    fun logCurrentMembershipIfMissingMembers() {
        var r: String? = null
        synchronized(this) {
            if (currentNumMembers < originalNumMembers) r =
                String.format("%d/%d members remain in cluster", currentNumMembers, originalNumMembers)
        }
        if (r != null) logger.log(r!!)
    }

    override fun memberRemoved(membershipEvent: MembershipEvent) {
        synchronized(this) {
            currentNumMembers--
            assert(currentNumMembers >= 0)
            logger.log("member removed, down to %d/%d members".formatted(currentNumMembers, originalNumMembers))
        }
    }

    override fun memberAdded(membershipEvent: MembershipEvent) {
        val sb = StringBuilder("member added")
        synchronized(this) {
            currentNumMembers++
            assert(currentNumMembers <= originalNumMembers)
            if (currentNumMembers == originalNumMembers) sb.append(
                ", %d/%d members back in cluster".formatted(
                    currentNumMembers,
                    originalNumMembers
                )
            )
            else sb.append(", up to %d/%d members".formatted(currentNumMembers, originalNumMembers))
        }
        logger.log(sb.toString())
    }
}
