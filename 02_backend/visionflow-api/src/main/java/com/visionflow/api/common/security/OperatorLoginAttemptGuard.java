package com.visionflow.api.common.security;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Base64;
import java.util.Comparator;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

@Component
public class OperatorLoginAttemptGuard {

    private static final String UNKNOWN_CLIENT = "unknown";

    private final int maximumFailures;
    private final Duration failureWindow;
    private final Duration lockDuration;
    private final int maximumTrackedClients;
    private final Clock clock;
    private final byte[] fingerprintSalt;
    private final ConcurrentMap<String, AttemptEntry> attempts =
            new ConcurrentHashMap<>();

    @Autowired
    public OperatorLoginAttemptGuard(
            @Value("${visionflow.security.operator.login-guard.maximum-failures:5}")
            int maximumFailures,

            @Value("${visionflow.security.operator.login-guard.window:PT10M}")
            Duration failureWindow,

            @Value("${visionflow.security.operator.login-guard.lock-duration:PT15M}")
            Duration lockDuration,

            @Value("${visionflow.security.operator.login-guard.maximum-tracked-clients:10000}")
            int maximumTrackedClients
    ) {
        this(
                maximumFailures,
                failureWindow,
                lockDuration,
                maximumTrackedClients,
                Clock.systemUTC()
        );
    }

    OperatorLoginAttemptGuard(
            int maximumFailures,
            Duration failureWindow,
            Duration lockDuration,
            int maximumTrackedClients,
            Clock clock
    ) {
        if (maximumFailures < 1) {
            throw new IllegalStateException("로그인 최대 실패 횟수는 1 이상이어야 합니다.");
        }
        if (failureWindow == null || failureWindow.isZero() || failureWindow.isNegative()) {
            throw new IllegalStateException("로그인 실패 집계 시간은 0보다 커야 합니다.");
        }
        if (lockDuration == null || lockDuration.isZero() || lockDuration.isNegative()) {
            throw new IllegalStateException("로그인 잠금 시간은 0보다 커야 합니다.");
        }
        if (maximumTrackedClients < 1) {
            throw new IllegalStateException("로그인 추적 클라이언트 수는 1 이상이어야 합니다.");
        }
        this.maximumFailures = maximumFailures;
        this.failureWindow = failureWindow;
        this.lockDuration = lockDuration;
        this.maximumTrackedClients = maximumTrackedClients;
        this.clock = clock;
        this.fingerprintSalt = new byte[32];
        new SecureRandom().nextBytes(this.fingerprintSalt);
    }

    public synchronized AttemptDecision inspect(String clientFingerprint) {
        String client = normalizeFingerprint(clientFingerprint);
        Instant now = clock.instant();
        AttemptEntry current = attempts.get(client);
        if (current == null) {
            return allowed(0);
        }
        if (isLockActive(current, now)) {
            return locked(current, now);
        }
        if (isExpired(current, now)) {
            attempts.remove(client, current);
            return allowed(0);
        }
        return allowed(current.failureCount());
    }

    public synchronized AttemptDecision recordFailure(String clientFingerprint) {
        String client = normalizeFingerprint(clientFingerprint);
        Instant now = clock.instant();
        AttemptEntry previous = attempts.get(client);
        if (previous != null && isLockActive(previous, now)) {
            return locked(previous, now);
        }

        if (previous == null || isExpired(previous, now)) {
            ensureCapacity(client);
            previous = new AttemptEntry(0, now, null, now);
        }

        int failureCount = previous.failureCount() + 1;
        Instant lockedUntil = failureCount >= maximumFailures
                ? now.plus(lockDuration)
                : null;
        AttemptEntry updated = new AttemptEntry(
                failureCount,
                previous.firstFailureAt(),
                lockedUntil,
                now
        );
        attempts.put(client, updated);
        return lockedUntil == null ? allowed(failureCount) : locked(updated, now);
    }

    public synchronized void recordSuccess(String clientFingerprint) {
        attempts.remove(normalizeFingerprint(clientFingerprint));
    }

    public String fingerprint(String remoteAddress) {
        String source = remoteAddress == null || remoteAddress.isBlank()
                ? UNKNOWN_CLIENT
                : remoteAddress.trim();
        return "client-" + digest(source).substring(0, 16);
    }

    private AttemptDecision allowed(int failureCount) {
        return new AttemptDecision(
                true,
                failureCount,
                Math.max(0, maximumFailures - failureCount),
                0
        );
    }

    private AttemptDecision locked(AttemptEntry entry, Instant now) {
        long remainingMillis = Duration.between(now, entry.lockedUntil()).toMillis();
        long retryAfterSeconds = Math.max(
                1,
                (remainingMillis + 999) / 1_000
        );
        return new AttemptDecision(
                false,
                entry.failureCount(),
                0,
                retryAfterSeconds
        );
    }

    private boolean isLockActive(AttemptEntry entry, Instant now) {
        return entry.lockedUntil() != null && entry.lockedUntil().isAfter(now);
    }

    private boolean isExpired(AttemptEntry entry, Instant now) {
        if (entry.lockedUntil() != null) {
            return !entry.lockedUntil().isAfter(now);
        }
        return !entry.firstFailureAt().plus(failureWindow).isAfter(now);
    }

    private void ensureCapacity(String incomingClient) {
        if (attempts.containsKey(incomingClient) || attempts.size() < maximumTrackedClients) {
            return;
        }
        attempts.entrySet().stream()
                .min(Comparator.comparing(entry -> entry.getValue().lastObservedAt()))
                .ifPresent(entry -> attempts.remove(entry.getKey(), entry.getValue()));
    }

    private String normalizeFingerprint(String clientFingerprint) {
        return clientFingerprint == null || clientFingerprint.isBlank()
                ? fingerprint(UNKNOWN_CLIENT)
                : clientFingerprint.trim();
    }

    private String digest(String value) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            digest.update(fingerprintSalt);
            byte[] bytes = digest.digest(value.getBytes(StandardCharsets.UTF_8));
            return Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("SHA-256 알고리즘을 사용할 수 없습니다.", exception);
        }
    }

    public record AttemptDecision(
            boolean allowed,
            int failureCount,
            int remainingAttempts,
            long retryAfterSeconds
    ) {
    }

    private record AttemptEntry(
            int failureCount,
            Instant firstFailureAt,
            Instant lockedUntil,
            Instant lastObservedAt
    ) {
    }
}
