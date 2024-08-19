package com.bbclient;

import com.hazelcast.cluster.MembershipEvent;
import com.hazelcast.cluster.MembershipListener;

public class ClientMembershipListener implements MembershipListener {
    private final Logger logger = new Logger("Membership");

    /*
     * Synchronized
     */
    private final int originalNumMembers;
    private int currentNumMembers;

    public ClientMembershipListener(int originalNumMembers) {
        logger.log("Initializing new %s() with %d members".formatted(this.getClass().getSimpleName(),
                originalNumMembers));
        synchronized (this) {
            this.originalNumMembers = originalNumMembers;
            this.currentNumMembers = this.originalNumMembers;
        }
    }

    public synchronized boolean clusterIsMissingMembers() {
        return currentNumMembers < originalNumMembers;
    }

    public void logCurrentMembershipIfMissingMembers() {
        String r = null;
        synchronized (this) {
            if (currentNumMembers < originalNumMembers)
                r = String.format("%d/%d members remain in cluster", currentNumMembers, originalNumMembers);
        }
        if (r != null)
            logger.log(r);
    }

    @Override
    public void memberRemoved(MembershipEvent membershipEvent) {
        synchronized (this) {
            currentNumMembers--;
            assert currentNumMembers >= 0;
            logger.log("member removed, down to %d/%d members".formatted(currentNumMembers, originalNumMembers));
        }
    }

    @Override
    public void memberAdded(MembershipEvent membershipEvent) {
        StringBuilder sb = new StringBuilder("member added");
        synchronized (this) {
            currentNumMembers++;
            assert currentNumMembers <= originalNumMembers;
            if (currentNumMembers == originalNumMembers)
                sb.append(", %d/%d members back in cluster".formatted(currentNumMembers, originalNumMembers));
            else
                sb.append(", up to %d/%d members".formatted(currentNumMembers, originalNumMembers));
        }
        logger.log(sb.toString());
    }
}
