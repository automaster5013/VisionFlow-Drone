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
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

@Component
public class OperatorSessionRegistry {

    private static final int TOKEN_BYTES = 32;
    private static final SecureRandom SECURE_RANDOM = new SecureRandom();

    private final Duration ttl;
    private final Duration idleTimeout;
    private final int maximumActiveSessions;
    private final Clock clock;
    private final ConcurrentMap<String, SessionEntry> sessions =
            new ConcurrentHashMap<>();

    @Autowired
    public OperatorSessionRegistry(
            @Value("${visionflow.security.operator.session.ttl:PT8H}")
            Duration ttl,

            @Value("${visionflow.security.operator.session.idle-timeout:PT30M}")
            Duration idleTimeout,

            @Value("${visionflow.security.operator.session.maximum-active:1000}")
            int maximumActiveSessions
    ) {
        this(ttl, idleTimeout, maximumActiveSessions, Clock.systemUTC());
    }

    OperatorSessionRegistry(Duration ttl, int maximumActiveSessions) {
        this(
                ttl,
                Duration.ofMinutes(30),
                maximumActiveSessions,
                Clock.systemUTC()
        );
    }

    OperatorSessionRegistry(
            Duration ttl,
            Duration idleTimeout,
            int maximumActiveSessions,
            Clock clock
    ) {
        if (ttl == null || ttl.isNegative() || ttl.isZero()) {
            throw new IllegalStateException("운영자 세션 만료 시간은 0보다 커야 합니다.");
        }
        if (idleTimeout == null || idleTimeout.isNegative() || idleTimeout.isZero()) {
            throw new IllegalStateException("운영자 세션 유휴 만료 시간은 0보다 커야 합니다.");
        }
        if (maximumActiveSessions < 1) {
            throw new IllegalStateException("운영자 최대 활성 세션 수는 1 이상이어야 합니다.");
        }
        if (clock == null) {
            throw new IllegalArgumentException("운영자 세션 시계가 필요합니다.");
        }
        this.ttl = ttl;
        this.idleTimeout = idleTimeout;
        this.maximumActiveSessions = maximumActiveSessions;
        this.clock = clock;
    }

    public synchronized OperatorSession issue(OperatorPrincipal principal) {
        return issue(principal, "client-unavailable");
    }

    public synchronized OperatorSession issue(
            OperatorPrincipal principal,
            String clientFingerprint
    ) {
        if (principal == null) {
            throw new IllegalArgumentException("운영자 정보가 필요합니다.");
        }

        Instant now = clock.instant();
        removeExpired(now);
        ensureCapacity();

        byte[] randomBytes = new byte[TOKEN_BYTES];
        SECURE_RANDOM.nextBytes(randomBytes);
        String token = Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(randomBytes);
        UUID sessionId = UUID.randomUUID();
        Instant expiresAt = now.plus(ttl);

        sessions.put(
                digest(token),
                new SessionEntry(
                        sessionId,
                        principal,
                        now,
                        now,
                        expiresAt,
                        normalizeClientFingerprint(clientFingerprint)
                )
        );
        return new OperatorSession(token, sessionId, principal, now, expiresAt);
    }

    public Optional<OperatorPrincipal> resolve(String presentedToken) {
        if (presentedToken == null || presentedToken.isBlank()) {
            return Optional.empty();
        }

        String tokenDigest = digest(presentedToken.trim());
        Instant now = clock.instant();
        SessionEntry entry = sessions.computeIfPresent(
                tokenDigest,
                (key, current) -> isActive(current, now)
                        ? current.seenAt(now)
                        : null
        );
        return entry == null
                ? Optional.empty()
                : Optional.of(entry.principal());
    }

    public Optional<OperatorSessionSummary> revoke(String presentedToken) {
        if (presentedToken == null || presentedToken.isBlank()) {
            return Optional.empty();
        }
        SessionEntry removed = sessions.remove(digest(presentedToken.trim()));
        return removed == null
                ? Optional.empty()
                : Optional.of(removed.toSummary(true, idleTimeout));
    }

    public synchronized Optional<OperatorSessionSummary> findByToken(
            String presentedToken
    ) {
        if (presentedToken == null || presentedToken.isBlank()) {
            return Optional.empty();
        }
        Instant now = clock.instant();
        removeExpired(now);
        SessionEntry entry = sessions.get(digest(presentedToken.trim()));
        return entry == null
                ? Optional.empty()
                : Optional.of(entry.toSummary(true, idleTimeout));
    }

    public synchronized List<OperatorSessionSummary> findAll(
            String currentToken
    ) {
        removeExpired(clock.instant());
        String currentDigest = currentToken == null || currentToken.isBlank()
                ? null
                : digest(currentToken.trim());
        return sessions.entrySet().stream()
                .map(entry -> entry.getValue().toSummary(
                        entry.getKey().equals(currentDigest),
                        idleTimeout
                ))
                .sorted(
                        Comparator.comparing(
                                OperatorSessionSummary::issuedAt,
                                Comparator.reverseOrder()
                        )
                )
                .toList();
    }

    public synchronized Optional<OperatorSessionSummary> revokeById(
            UUID sessionId
    ) {
        if (sessionId == null) {
            return Optional.empty();
        }
        removeExpired(clock.instant());
        Optional<Map.Entry<String, SessionEntry>> target = sessions
                .entrySet()
                .stream()
                .filter(entry -> entry.getValue().sessionId().equals(sessionId))
                .findFirst();
        if (target.isEmpty()) {
            return Optional.empty();
        }
        Map.Entry<String, SessionEntry> entry = target.get();
        return sessions.remove(entry.getKey(), entry.getValue())
                ? Optional.of(entry.getValue().toSummary(false, idleTimeout))
                : Optional.empty();
    }

    public synchronized List<OperatorSessionSummary> revokeAllExcept(
            String preservedToken
    ) {
        removeExpired(clock.instant());
        String preservedDigest = preservedToken == null || preservedToken.isBlank()
                ? null
                : digest(preservedToken.trim());
        List<Map.Entry<String, SessionEntry>> targets = sessions
                .entrySet()
                .stream()
                .filter(entry -> !entry.getKey().equals(preservedDigest))
                .toList();
        return targets.stream()
                .filter(entry -> sessions.remove(entry.getKey(), entry.getValue()))
                .map(entry -> entry.getValue().toSummary(false, idleTimeout))
                .toList();
    }

    int activeSessionCount() {
        removeExpired(clock.instant());
        return sessions.size();
    }

    private void removeExpired(Instant now) {
        sessions.entrySet().removeIf(
                entry -> !isActive(entry.getValue(), now)
        );
    }

    private boolean isActive(SessionEntry entry, Instant now) {
        return entry.expiresAt().isAfter(now)
                && entry.lastSeenAt().plus(idleTimeout).isAfter(now);
    }

    private void ensureCapacity() {
        while (sessions.size() >= maximumActiveSessions) {
            sessions.entrySet().stream()
                    .min(Comparator.comparing(entry -> entry.getValue().issuedAt()))
                    .ifPresentOrElse(
                            entry -> sessions.remove(entry.getKey(), entry.getValue()),
                            () -> {
                                throw new IllegalStateException(
                                        "운영자 세션 저장소 용량을 확보하지 못했습니다."
                                );
                            }
                    );
        }
    }

    private String normalizeClientFingerprint(String clientFingerprint) {
        if (clientFingerprint == null || clientFingerprint.isBlank()) {
            return "client-unavailable";
        }
        String normalized = clientFingerprint.trim();
        return normalized.length() <= 80
                ? normalized
                : normalized.substring(0, 80);
    }

    private String digest(String token) {
        try {
            byte[] bytes = MessageDigest.getInstance("SHA-256")
                    .digest(token.getBytes(StandardCharsets.UTF_8));
            return Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("SHA-256 알고리즘을 사용할 수 없습니다.", exception);
        }
    }

    private record SessionEntry(
            UUID sessionId,
            OperatorPrincipal principal,
            Instant issuedAt,
            Instant lastSeenAt,
            Instant expiresAt,
            String clientFingerprint
    ) {
        private SessionEntry seenAt(Instant value) {
            return new SessionEntry(
                    sessionId,
                    principal,
                    issuedAt,
                    value,
                    expiresAt,
                    clientFingerprint
            );
        }

        private OperatorSessionSummary toSummary(
                boolean current,
                Duration idleTimeout
        ) {
            Instant idleExpiresAt = lastSeenAt.plus(idleTimeout);
            if (idleExpiresAt.isAfter(expiresAt)) {
                idleExpiresAt = expiresAt;
            }
            return new OperatorSessionSummary(
                    sessionId,
                    principal.username(),
                    principal.role(),
                    issuedAt,
                    lastSeenAt,
                    idleExpiresAt,
                    expiresAt,
                    clientFingerprint,
                    current
            );
        }
    }
}
