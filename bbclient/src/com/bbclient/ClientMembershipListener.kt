package com.bbclient

import com.hazelcast.cluster.MembershipEvent
import com.hazelcast.cluster.MembershipListener
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

class ClientMembershipListener(private var originalNumMembers: Int) : MembershipListener {
    private var logger: Logger = Logger("Membership")

    /*
     * Thread-safe via Mutex
     */
    private var mutex = Mutex()
    private var currentNumMembers = originalNumMembers

    init {
        logger.log(
            "Initializing new %s() with %d members".format(
                javaClass.simpleName,
                originalNumMembers
            )
        )
    }

    fun clusterIsMissingMembers() = runBlocking {
        mutex.withLock {
            currentNumMembers < originalNumMembers
        }
    }

    private fun getMembershipStatus() = "$currentNumMembers/$originalNumMembers"

    fun logCurrentMembershipIfMissingMembers() = runBlocking {
        mutex.withLock {
            if (currentNumMembers < originalNumMembers)
                logger.log(getMembershipStatus() + " members remain in cluster")
        }
    }

    override fun memberRemoved(membershipEvent: MembershipEvent) {
        runBlocking {
            mutex.withLock {
                currentNumMembers--
                assert(currentNumMembers >= 0)
                logger.log("member removed, down to ${getMembershipStatus()} members")
            }
        }
    }

    override fun memberAdded(membershipEvent: MembershipEvent) {
        runBlocking {
            val sb = StringBuilder("member added")
            mutex.withLock {
                currentNumMembers++
                assert(currentNumMembers <= originalNumMembers)
                if (currentNumMembers == originalNumMembers)
                    sb.append(", ${getMembershipStatus()} members back in cluster")
                else
                    sb.append(", up to ${getMembershipStatus()} members")
            }
            logger.log(sb.toString())
        }
    }
}
