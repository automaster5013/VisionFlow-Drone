package com.visionflow.api.common.security;

import org.junit.jupiter.api.Test;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

class OperatorSessionRegistryTests {

    @Test
    void issuedSessionCanBeResolvedAndRevoked() {
        OperatorSessionRegistry registry =
                new OperatorSessionRegistry(Duration.ofHours(8), 10);
        OperatorPrincipal principal =
                new OperatorPrincipal("test-operator", OperatorRole.OPERATOR);

        OperatorSession session = registry.issue(principal);

        assertThat(session.token()).hasSizeGreaterThanOrEqualTo(40);
        assertThat(registry.resolve(session.token())).contains(principal);
        assertThat(registry.activeSessionCount()).isEqualTo(1);

        registry.revoke(session.token());

        assertThat(registry.resolve(session.token())).isEmpty();
        assertThat(registry.activeSessionCount()).isZero();
    }

    @Test
    void oldestSessionIsRemovedWhenCapacityIsReached() {
        OperatorSessionRegistry registry =
                new OperatorSessionRegistry(Duration.ofHours(8), 1);
        OperatorPrincipal principal =
                new OperatorPrincipal("test-admin", OperatorRole.ADMIN);

        OperatorSession first = registry.issue(principal);
        OperatorSession second = registry.issue(principal);

        assertThat(registry.resolve(first.token())).isEmpty();
        assertThat(registry.resolve(second.token())).contains(principal);
        assertThat(registry.activeSessionCount()).isEqualTo(1);
    }

    @Test
    void listsSessionsWithoutExposingTokensAndMarksCurrentSession() {
        OperatorSessionRegistry registry =
                new OperatorSessionRegistry(Duration.ofHours(8), 10);
        OperatorPrincipal viewer =
                new OperatorPrincipal("test-viewer", OperatorRole.VIEWER);
        OperatorPrincipal administrator =
                new OperatorPrincipal("test-admin", OperatorRole.ADMIN);

        OperatorSession first = registry.issue(viewer, "client-a");
        OperatorSession second = registry.issue(administrator, "client-b");

        List<OperatorSessionSummary> sessions = registry.findAll(second.token());

        assertThat(sessions).hasSize(2);
        assertThat(sessions)
                .extracting(OperatorSessionSummary::sessionId)
                .containsExactlyInAnyOrder(first.sessionId(), second.sessionId());
        assertThat(sessions)
                .filteredOn(OperatorSessionSummary::current)
                .singleElement()
                .extracting(OperatorSessionSummary::sessionId)
                .isEqualTo(second.sessionId());
        assertThat(sessions)
                .extracting(OperatorSessionSummary::clientFingerprint)
                .containsExactlyInAnyOrder("client-a", "client-b");
    }

    @Test
    void revokesSessionByPublicSessionId() {
        OperatorSessionRegistry registry =
                new OperatorSessionRegistry(Duration.ofHours(8), 10);
        OperatorPrincipal principal =
                new OperatorPrincipal("test-operator", OperatorRole.OPERATOR);
        OperatorSession session = registry.issue(principal, "client-a");

        assertThat(registry.revokeById(session.sessionId()))
                .get()
                .extracting(OperatorSessionSummary::username)
                .isEqualTo("test-operator");
        assertThat(registry.resolve(session.token())).isEmpty();
        assertThat(registry.revokeById(session.sessionId())).isEmpty();
    }

    @Test
    void expiresSessionAfterConfiguredIdleTimeout() {
        MutableClock clock = new MutableClock(
                Instant.parse("2026-07-23T00:00:00Z")
        );
        OperatorSessionRegistry registry = new OperatorSessionRegistry(
                Duration.ofHours(8),
                Duration.ofMinutes(30),
                10,
                clock
        );
        OperatorPrincipal principal =
                new OperatorPrincipal("idle-operator", OperatorRole.OPERATOR);

        OperatorSession session = registry.issue(principal);
        clock.advance(Duration.ofMinutes(29));
        assertThat(registry.resolve(session.token())).contains(principal);

        clock.advance(Duration.ofMinutes(31));
        assertThat(registry.resolve(session.token())).isEmpty();
        assertThat(registry.activeSessionCount()).isZero();
    }

    @Test
    void absoluteExpiryCannotBeExtendedByActivity() {
        MutableClock clock = new MutableClock(
                Instant.parse("2026-07-23T00:00:00Z")
        );
        OperatorSessionRegistry registry = new OperatorSessionRegistry(
                Duration.ofHours(1),
                Duration.ofMinutes(30),
                10,
                clock
        );
        OperatorPrincipal principal =
                new OperatorPrincipal("absolute-operator", OperatorRole.ADMIN);

        OperatorSession session = registry.issue(principal);
        clock.advance(Duration.ofMinutes(20));
        assertThat(registry.resolve(session.token())).contains(principal);
        clock.advance(Duration.ofMinutes(20));
        assertThat(registry.resolve(session.token())).contains(principal);

        clock.advance(Duration.ofMinutes(21));
        assertThat(registry.resolve(session.token())).isEmpty();
    }

    @Test
    void sessionSummaryShowsEffectiveIdleExpiry() {
        MutableClock clock = new MutableClock(
                Instant.parse("2026-07-23T00:00:00Z")
        );
        OperatorSessionRegistry registry = new OperatorSessionRegistry(
                Duration.ofHours(8),
                Duration.ofMinutes(30),
                10,
                clock
        );
        OperatorSession session = registry.issue(
                new OperatorPrincipal("summary-admin", OperatorRole.ADMIN)
        );

        assertThat(registry.findByToken(session.token()))
                .get()
                .extracting(OperatorSessionSummary::idleExpiresAt)
                .isEqualTo(Instant.parse("2026-07-23T00:30:00Z"));
    }

    @Test
    void bulkRevocationPreservesOnlyCurrentSession() {
        OperatorSessionRegistry registry =
                new OperatorSessionRegistry(Duration.ofHours(8), 10);
        OperatorSession current = registry.issue(
                new OperatorPrincipal("current-admin", OperatorRole.ADMIN)
        );
        OperatorSession viewer = registry.issue(
                new OperatorPrincipal("other-viewer", OperatorRole.VIEWER)
        );
        OperatorSession operator = registry.issue(
                new OperatorPrincipal("other-operator", OperatorRole.OPERATOR)
        );

        List<OperatorSessionSummary> revoked = registry.revokeAllExcept(
                current.token()
        );

        assertThat(revoked)
                .extracting(OperatorSessionSummary::sessionId)
                .containsExactlyInAnyOrder(viewer.sessionId(), operator.sessionId());
        assertThat(registry.resolve(current.token())).isPresent();
        assertThat(registry.resolve(viewer.token())).isEmpty();
        assertThat(registry.resolve(operator.token())).isEmpty();
        assertThat(registry.activeSessionCount()).isEqualTo(1);
    }

    @Test
    void bulkRevocationWithoutCurrentTokenRemovesEverySession() {
        OperatorSessionRegistry registry =
                new OperatorSessionRegistry(Duration.ofHours(8), 10);
        registry.issue(
                new OperatorPrincipal("first-operator", OperatorRole.OPERATOR)
        );
        registry.issue(
                new OperatorPrincipal("second-admin", OperatorRole.ADMIN)
        );

        assertThat(registry.revokeAllExcept(null)).hasSize(2);
        assertThat(registry.activeSessionCount()).isZero();
    }

    private static final class MutableClock extends Clock {

        private Instant instant;

        private MutableClock(Instant instant) {
            this.instant = instant;
        }

        private void advance(Duration duration) {
            instant = instant.plus(duration);
        }

        @Override
        public ZoneId getZone() {
            return ZoneOffset.UTC;
        }

        @Override
        public Clock withZone(ZoneId zone) {
            return this;
        }

        @Override
        public Instant instant() {
            return instant;
        }
    }
}
