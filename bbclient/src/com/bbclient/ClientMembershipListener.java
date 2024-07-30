package com.bbclient;

import com.hazelcast.cluster.MembershipEvent;
import com.hazelcast.cluster.MembershipListener;

public class ClientMembershipListener implements MembershipListener {
    @Override
    public void memberRemoved(MembershipEvent membershipEvent) {
        log("memberRemoved() -> %s".formatted(membershipEvent));
    }

    @Override
    public void memberAdded(MembershipEvent membershipEvent) {
        log("memberAdded() -> %s".formatted(membershipEvent));

    }
}
