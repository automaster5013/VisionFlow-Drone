package com.visionflow.api.common.security;

import org.junit.jupiter.api.Test;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;

import static org.assertj.core.api.Assertions.assertThat;

class OperatorLoginAttemptGuardTests {

    @Test
    void locksClientAtConfiguredFailureThreshold() {
        MutableClock clock = new MutableClock(Instant.parse("2026-07-23T00:00:00Z"));
        OperatorLoginAttemptGuard guard = guard(clock);

        OperatorLoginAttemptGuard.AttemptDecision first =
                guard.recordFailure("client-a");
        OperatorLoginAttemptGuard.AttemptDecision second =
                guard.recordFailure("client-a");
        OperatorLoginAttemptGuard.AttemptDecision third =
                guard.recordFailure("client-a");

        assertThat(first.allowed()).isTrue();
        assertThat(first.remainingAttempts()).isEqualTo(2);
        assertThat(second.allowed()).isTrue();
        assertThat(second.remainingAttempts()).isEqualTo(1);
        assertThat(third.allowed()).isFalse();
        assertThat(third.failureCount()).isEqualTo(3);
        assertThat(third.retryAfterSeconds()).isEqualTo(900);
        assertThat(guard.inspect("client-a").allowed()).isFalse();
    }

    @Test
    void successfulLoginClearsFailures() {
        OperatorLoginAttemptGuard guard = guard(
                new MutableClock(Instant.parse("2026-07-23T00:00:00Z"))
        );
        guard.recordFailure("client-a");
        guard.recordFailure("client-a");

        guard.recordSuccess("client-a");

        OperatorLoginAttemptGuard.AttemptDecision decision =
                guard.inspect("client-a");
        assertThat(decision.allowed()).isTrue();
        assertThat(decision.failureCount()).isZero();
        assertThat(decision.remainingAttempts()).isEqualTo(3);
    }

    @Test
    void expiredLockAllowsFreshAttempts() {
        MutableClock clock = new MutableClock(Instant.parse("2026-07-23T00:00:00Z"));
        OperatorLoginAttemptGuard guard = guard(clock);
        guard.recordFailure("client-a");
        guard.recordFailure("client-a");
        guard.recordFailure("client-a");

        clock.advance(Duration.ofMinutes(15));

        OperatorLoginAttemptGuard.AttemptDecision decision =
                guard.inspect("client-a");
        assertThat(decision.allowed()).isTrue();
        assertThat(decision.failureCount()).isZero();
    }

    @Test
    void clientFingerprintDoesNotExposeRemoteAddress() {
        OperatorLoginAttemptGuard guard = guard(
                new MutableClock(Instant.parse("2026-07-23T00:00:00Z"))
        );

        String fingerprint = guard.fingerprint("192.168.10.106");

        assertThat(fingerprint).startsWith("client-");
        assertThat(fingerprint).doesNotContain("192.168.10.106");
        assertThat(guard.fingerprint("192.168.10.106")).isEqualTo(fingerprint);
    }

    @Test
    void loginAttemptsFromOneProxyAreIsolatedByCaseInsensitiveUsername() {
        OperatorLoginAttemptGuard guard = guard(
                new MutableClock(Instant.parse("2026-07-23T00:00:00Z"))
        );
        String firstUser = guard.attemptFingerprint(
                "172.18.0.4",
                "USER:operator"
        );
        String sameUserDifferentCase = guard.attemptFingerprint(
                "172.18.0.4",
                "USER:Operator"
        );
        String secondUser = guard.attemptFingerprint(
                "172.18.0.4",
                "USER:admin"
        );
        String differentlyCasedApiKey = guard.attemptFingerprint(
                "172.18.0.4",
                "API_KEY:AbC123"
        );
        String apiKey = guard.attemptFingerprint(
                "172.18.0.4",
                "API_KEY:abc123"
        );

        assertThat(firstUser).isEqualTo(sameUserDifferentCase);
        assertThat(firstUser).isNotEqualTo(secondUser);
        assertThat(differentlyCasedApiKey).isNotEqualTo(apiKey);

        guard.recordFailure(firstUser);
        guard.recordFailure(firstUser);
        guard.recordFailure(firstUser);

        assertThat(guard.inspect(firstUser).allowed()).isFalse();
        assertThat(guard.inspect(secondUser).allowed()).isTrue();
    }

    private OperatorLoginAttemptGuard guard(Clock clock) {
        return new OperatorLoginAttemptGuard(
                3,
                Duration.ofMinutes(10),
                Duration.ofMinutes(15),
                100,
                clock
        );
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
