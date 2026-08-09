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
import java.util.Locale;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

@Component
public class OperatorPairingRegistry {

    private static final int TOKEN_BYTES = 32;
    private static final int MAXIMUM_DEVICE_NAME_LENGTH = 80;
    private static final SecureRandom SECURE_RANDOM = new SecureRandom();

    private final Duration ttl;
    private final int maximumActivePairings;
    private final OperatorSessionRegistry sessionRegistry;
    private final Clock clock;
    private final ConcurrentMap<UUID, PairingEntry> pairings =
            new ConcurrentHashMap<>();

    @Autowired
    public OperatorPairingRegistry(
            @Value("${visionflow.security.operator.pairing.ttl:PT5M}")
            Duration ttl,

            @Value("${visionflow.security.operator.pairing.maximum-active:100}")
            int maximumActivePairings,

            OperatorSessionRegistry sessionRegistry
    ) {
        this(
                ttl,
                maximumActivePairings,
                sessionRegistry,
                Clock.systemUTC()
        );
    }

    OperatorPairingRegistry(
            Duration ttl,
            int maximumActivePairings,
            OperatorSessionRegistry sessionRegistry,
            Clock clock
    ) {
        if (ttl == null || ttl.isZero() || ttl.isNegative()) {
            throw new IllegalStateException(
                    "운영자 페어링 만료 시간은 0보다 커야 합니다."
            );
        }
        if (maximumActivePairings < 1) {
            throw new IllegalStateException(
                    "운영자 최대 활성 페어링 수는 1 이상이어야 합니다."
            );
        }
        if (sessionRegistry == null) {
            throw new IllegalArgumentException("운영자 세션 저장소가 필요합니다.");
        }
        if (clock == null) {
            throw new IllegalArgumentException("운영자 페어링 시계가 필요합니다.");
        }
        this.ttl = ttl;
        this.maximumActivePairings = maximumActivePairings;
        this.sessionRegistry = sessionRegistry;
        this.clock = clock;
    }

    public synchronized Creation create(
            UUID issuerSessionId,
            OperatorPrincipal issuer,
            OperatorPrincipal target
    ) {
        if (issuerSessionId == null || issuer == null || target == null) {
            throw new IllegalArgumentException(
                    "페어링 발급 세션과 운영자 정보가 필요합니다."
            );
        }

        Instant now = clock.instant();
        removeExpired(now);
        ensureCapacity();

        byte[] randomBytes = new byte[TOKEN_BYTES];
        SECURE_RANDOM.nextBytes(randomBytes);
        String token = Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(randomBytes);
        UUID pairingId = UUID.randomUUID();
        String verificationCode = String.format(
                Locale.ROOT,
                "%06d",
                SECURE_RANDOM.nextInt(1_000_000)
        );
        Instant expiresAt = now.plus(ttl);

        PairingEntry entry = new PairingEntry(
                pairingId,
                digest(token),
                verificationCode,
                issuerSessionId,
                issuer,
                target,
                PairingStatus.PENDING,
                now,
                expiresAt
        );
        pairings.put(pairingId, entry);

        return new Creation(
                pairingId,
                token,
                verificationCode,
                target.role(),
                PairingStatus.PENDING,
                expiresAt
        );
    }

    public synchronized Snapshot claim(
            UUID pairingId,
            String presentedToken,
            String deviceName
    ) {
        PairingEntry entry = requirePairing(pairingId);
        verifyToken(entry, presentedToken);
        ensureNotExpired(entry);
        String normalizedDeviceName = normalizeDeviceName(deviceName);

        if (entry.status == PairingStatus.PENDING) {
            entry.status = PairingStatus.CLAIMED;
            entry.deviceName = normalizedDeviceName;
            entry.claimedAt = clock.instant();
            return snapshot(entry);
        }
        if (
                entry.status == PairingStatus.CLAIMED
                        || entry.status == PairingStatus.APPROVED
        ) {
            return snapshot(entry);
        }

        throw gone(entry.status);
    }

    public synchronized Snapshot status(
            UUID pairingId,
            UUID issuerSessionId
    ) {
        PairingEntry entry = requirePairing(pairingId);
        requireIssuer(entry, issuerSessionId);
        ensureNotExpired(entry);
        return snapshot(entry);
    }

    public synchronized Snapshot approve(
            UUID pairingId,
            UUID issuerSessionId
    ) {
        PairingEntry entry = requirePairing(pairingId);
        requireIssuer(entry, issuerSessionId);
        ensureNotExpired(entry);

        if (entry.status == PairingStatus.PENDING) {
            throw new PairingException(
                    Failure.CONFLICT,
                    "OPERATOR_PAIRING_NOT_CLAIMED",
                    "스마트폰이 QR 페어링 요청을 먼저 열어야 승인할 수 있습니다."
            );
        }
        if (entry.status == PairingStatus.CLAIMED) {
            entry.status = PairingStatus.APPROVED;
            entry.approvedAt = clock.instant();
            return snapshot(entry);
        }
        if (entry.status == PairingStatus.APPROVED) {
            return snapshot(entry);
        }

        throw gone(entry.status);
    }

    public synchronized Snapshot cancel(
            UUID pairingId,
            UUID issuerSessionId
    ) {
        PairingEntry entry = requirePairing(pairingId);
        requireIssuer(entry, issuerSessionId);
        ensureNotExpired(entry);

        if (entry.status == PairingStatus.CONSUMED) {
            throw gone(entry.status);
        }
        entry.status = PairingStatus.CANCELLED;
        return snapshot(entry);
    }

    public synchronized ExchangeResult exchange(
            UUID pairingId,
            String presentedToken
    ) {
        PairingEntry entry = requirePairing(pairingId);
        verifyToken(entry, presentedToken);
        ensureNotExpired(entry);

        if (
                entry.status == PairingStatus.PENDING
                        || entry.status == PairingStatus.CLAIMED
        ) {
            throw new PairingException(
                    Failure.CONFLICT,
                    "OPERATOR_PAIRING_APPROVAL_REQUIRED",
                    "PC에서 이 기기의 페어링 요청을 승인해 주세요."
            );
        }
        if (entry.status != PairingStatus.APPROVED) {
            throw gone(entry.status);
        }

        String clientFingerprint = "paired-"
                + normalizeClientLabel(entry.deviceName);
        OperatorSession session = sessionRegistry.issue(
                entry.target,
                clientFingerprint
        );
        entry.status = PairingStatus.CONSUMED;

        return new ExchangeResult(
                entry.pairingId,
                entry.target,
                entry.deviceName,
                session
        );
    }

    private PairingEntry requirePairing(UUID pairingId) {
        PairingEntry entry = pairingId == null
                ? null
                : pairings.get(pairingId);
        if (entry == null) {
            throw new PairingException(
                    Failure.NOT_FOUND,
                    "OPERATOR_PAIRING_NOT_FOUND",
                    "운영자 페어링 요청을 찾을 수 없습니다."
            );
        }
        return entry;
    }

    private void requireIssuer(
            PairingEntry entry,
            UUID issuerSessionId
    ) {
        if (
                issuerSessionId == null
                        || !entry.issuerSessionId.equals(issuerSessionId)
        ) {
            throw new PairingException(
                    Failure.FORBIDDEN,
                    "OPERATOR_PAIRING_ISSUER_MISMATCH",
                    "이 페어링 요청을 생성한 브라우저 세션에서만 관리할 수 있습니다."
            );
        }
    }

    private void verifyToken(
            PairingEntry entry,
            String presentedToken
    ) {
        if (presentedToken == null || presentedToken.isBlank()) {
            throw invalidToken();
        }
        byte[] actual = digest(presentedToken.trim())
                .getBytes(StandardCharsets.UTF_8);
        byte[] expected = entry.tokenDigest
                .getBytes(StandardCharsets.UTF_8);
        if (!MessageDigest.isEqual(actual, expected)) {
            throw invalidToken();
        }
    }

    private PairingException invalidToken() {
        return new PairingException(
                Failure.INVALID_TOKEN,
                "INVALID_OPERATOR_PAIRING_TOKEN",
                "운영자 페어링 토큰이 올바르지 않습니다."
        );
    }

    private void ensureNotExpired(PairingEntry entry) {
        if (!entry.expiresAt.isAfter(clock.instant())) {
            entry.status = PairingStatus.EXPIRED;
            throw gone(PairingStatus.EXPIRED);
        }
    }

    private PairingException gone(PairingStatus status) {
        String code = switch (status) {
            case EXPIRED -> "OPERATOR_PAIRING_EXPIRED";
            case CONSUMED -> "OPERATOR_PAIRING_ALREADY_USED";
            case CANCELLED -> "OPERATOR_PAIRING_CANCELLED";
            default -> "OPERATOR_PAIRING_UNAVAILABLE";
        };
        String message = switch (status) {
            case EXPIRED -> "운영자 페어링 요청이 만료되었습니다.";
            case CONSUMED -> "운영자 페어링 요청이 이미 사용되었습니다.";
            case CANCELLED -> "운영자 페어링 요청이 취소되었습니다.";
            default -> "운영자 페어링 요청을 더 이상 사용할 수 없습니다.";
        };
        return new PairingException(
                Failure.GONE,
                code,
                message
        );
    }

    private String normalizeDeviceName(String value) {
        String candidate = value == null ? "" : value.trim();
        if (candidate.isEmpty()) {
            candidate = "VisionFlow mobile";
        }
        if (candidate.length() > MAXIMUM_DEVICE_NAME_LENGTH) {
            throw new PairingException(
                    Failure.BAD_REQUEST,
                    "INVALID_OPERATOR_PAIRING_DEVICE_NAME",
                    "기기 이름은 80자 이하여야 합니다."
            );
        }
        if (candidate.chars().anyMatch(Character::isISOControl)) {
            throw new PairingException(
                    Failure.BAD_REQUEST,
                    "INVALID_OPERATOR_PAIRING_DEVICE_NAME",
                    "기기 이름에 제어 문자를 사용할 수 없습니다."
            );
        }
        return candidate;
    }

    private String normalizeClientLabel(String value) {
        String candidate = value == null || value.isBlank()
                ? "mobile"
                : value.trim();
        String normalized = candidate
                .replaceAll("[^\\p{L}\\p{N}._ -]+", "-")
                .replaceAll("\\s+", "-");
        if (normalized.isBlank()) {
            normalized = "mobile";
        }
        return normalized.length() <= 72
                ? normalized
                : normalized.substring(0, 72);
    }

    private Snapshot snapshot(PairingEntry entry) {
        return new Snapshot(
                entry.pairingId,
                entry.verificationCode,
                entry.target.role(),
                entry.status,
                entry.deviceName,
                entry.createdAt,
                entry.claimedAt,
                entry.approvedAt,
                entry.expiresAt
        );
    }

    private void removeExpired(Instant now) {
        pairings.entrySet().removeIf(entry ->
                !entry.getValue().expiresAt.isAfter(now)
        );
    }

    private void ensureCapacity() {
        while (pairings.size() >= maximumActivePairings) {
            Optional<PairingEntry> oldest = pairings
                    .values()
                    .stream()
                    .min(Comparator.comparing(value -> value.createdAt));
            if (oldest.isEmpty()) {
                throw new IllegalStateException(
                        "운영자 페어링 저장소 용량을 확보하지 못했습니다."
                );
            }
            pairings.remove(oldest.get().pairingId, oldest.get());
        }
    }

    private String digest(String token) {
        try {
            byte[] bytes = MessageDigest.getInstance("SHA-256")
                    .digest(token.getBytes(StandardCharsets.UTF_8));
            return Base64.getUrlEncoder()
                    .withoutPadding()
                    .encodeToString(bytes);
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException(
                    "SHA-256 알고리즘을 사용할 수 없습니다.",
                    exception
            );
        }
    }

    public enum PairingStatus {
        PENDING,
        CLAIMED,
        APPROVED,
        CONSUMED,
        CANCELLED,
        EXPIRED
    }

    public enum Failure {
        BAD_REQUEST,
        NOT_FOUND,
        INVALID_TOKEN,
        FORBIDDEN,
        CONFLICT,
        GONE
    }

    public static final class PairingException extends RuntimeException {
        private final Failure failure;
        private final String code;

        public PairingException(
                Failure failure,
                String code,
                String message
        ) {
            super(message);
            this.failure = failure;
            this.code = code;
        }

        public Failure failure() {
            return failure;
        }

        public String code() {
            return code;
        }
    }

    public record Creation(
            UUID pairingId,
            String pairingToken,
            String verificationCode,
            OperatorRole targetRole,
            PairingStatus status,
            Instant expiresAt
    ) {
    }

    public record Snapshot(
            UUID pairingId,
            String verificationCode,
            OperatorRole targetRole,
            PairingStatus status,
            String deviceName,
            Instant createdAt,
            Instant claimedAt,
            Instant approvedAt,
            Instant expiresAt
    ) {
    }

    public record ExchangeResult(
            UUID pairingId,
            OperatorPrincipal target,
            String deviceName,
            OperatorSession session
    ) {
    }

    private static final class PairingEntry {
        private final UUID pairingId;
        private final String tokenDigest;
        private final String verificationCode;
        private final UUID issuerSessionId;
        private final OperatorPrincipal issuer;
        private final OperatorPrincipal target;
        private PairingStatus status;
        private final Instant createdAt;
        private final Instant expiresAt;
        private String deviceName;
        private Instant claimedAt;
        private Instant approvedAt;

        private PairingEntry(
                UUID pairingId,
                String tokenDigest,
                String verificationCode,
                UUID issuerSessionId,
                OperatorPrincipal issuer,
                OperatorPrincipal target,
                PairingStatus status,
                Instant createdAt,
                Instant expiresAt
        ) {
            this.pairingId = pairingId;
            this.tokenDigest = tokenDigest;
            this.verificationCode = verificationCode;
            this.issuerSessionId = issuerSessionId;
            this.issuer = issuer;
            this.target = target;
            this.status = status;
            this.createdAt = createdAt;
            this.expiresAt = expiresAt;
        }
    }
}
