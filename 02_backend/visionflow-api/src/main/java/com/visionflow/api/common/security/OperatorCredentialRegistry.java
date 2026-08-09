package com.visionflow.api.common.security;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Optional;
import java.util.Set;

@Component
public class OperatorCredentialRegistry {

    private static final int MINIMUM_KEY_LENGTH = 24;
    private static final int MAXIMUM_NAME_LENGTH = 100;

    private final boolean enabled;
    private final List<Credential> credentials;

    public OperatorCredentialRegistry(
            @Value("${visionflow.security.operator.enabled:false}")
            boolean enabled,

            @Value("${visionflow.security.operator.viewer.name:viewer}")
            String viewerName,

            @Value("${visionflow.security.operator.viewer.key:}")
            String viewerKey,

            @Value("${visionflow.security.operator.operator.name:operator}")
            String operatorName,

            @Value("${visionflow.security.operator.operator.key:}")
            String operatorKey,

            @Value("${visionflow.security.operator.admin.name:admin}")
            String adminName,

            @Value("${visionflow.security.operator.admin.key:}")
            String adminKey
    ) {
        this.enabled = enabled;
        List<Credential> configured = new ArrayList<>();
        addCredential(configured, viewerName, viewerKey, OperatorRole.VIEWER);
        addCredential(configured, operatorName, operatorKey, OperatorRole.OPERATOR);
        addCredential(configured, adminName, adminKey, OperatorRole.ADMIN);
        validate(enabled, configured);
        this.credentials = List.copyOf(configured);
    }

    public boolean isEnabled() {
        return enabled;
    }

    public Optional<OperatorPrincipal> resolve(String presentedKey) {
        if (!enabled || presentedKey == null || presentedKey.isBlank()) {
            return Optional.empty();
        }

        byte[] candidate = presentedKey.trim().getBytes(StandardCharsets.UTF_8);
        for (Credential credential : credentials) {
            if (MessageDigest.isEqual(candidate, credential.keyBytes())) {
                return Optional.of(credential.principal());
            }
        }
        return Optional.empty();
    }

    public Optional<OperatorPrincipal> findPrincipal(OperatorRole role) {
        if (!enabled || role == null) {
            return Optional.empty();
        }
        return credentials.stream()
                .map(Credential::principal)
                .filter(principal -> principal.role() == role)
                .findFirst();
    }

    private void addCredential(
            List<Credential> target,
            String rawName,
            String rawKey,
            OperatorRole role
    ) {
        String key = rawKey == null ? "" : rawKey.trim();
        if (key.isEmpty()) {
            return;
        }
        if (key.length() < MINIMUM_KEY_LENGTH) {
            throw new IllegalStateException(
                    role + " 운영자 키는 " + MINIMUM_KEY_LENGTH + "자 이상이어야 합니다."
            );
        }

        String name = normalizeName(rawName, role);
        target.add(
                new Credential(
                        new OperatorPrincipal(name, role),
                        key,
                        key.getBytes(StandardCharsets.UTF_8)
                )
        );
    }

    private String normalizeName(String rawName, OperatorRole role) {
        String name = rawName == null ? "" : rawName.trim();
        if (name.isEmpty() || name.length() > MAXIMUM_NAME_LENGTH) {
            throw new IllegalStateException(
                    role + " 운영자 이름은 1~" + MAXIMUM_NAME_LENGTH + "자여야 합니다."
            );
        }
        if (name.chars().anyMatch(Character::isISOControl)) {
            throw new IllegalStateException(role + " 운영자 이름에 제어 문자를 사용할 수 없습니다.");
        }
        return name;
    }

    private void validate(boolean enabled, List<Credential> configured) {
        if (enabled && configured.isEmpty()) {
            throw new IllegalStateException(
                    "운영자 RBAC를 활성화하려면 VIEWER, OPERATOR, ADMIN 키 중 하나 이상을 설정해야 합니다."
            );
        }

        Set<String> keys = new HashSet<>();
        Set<String> names = new HashSet<>();
        for (Credential credential : configured) {
            if (!keys.add(credential.key())) {
                throw new IllegalStateException("운영자 역할별 키는 서로 달라야 합니다.");
            }
            String normalizedName = credential.principal()
                    .username()
                    .toLowerCase(Locale.ROOT);
            if (!names.add(normalizedName)) {
                throw new IllegalStateException("운영자 역할별 이름은 서로 달라야 합니다.");
            }
        }
    }

    private record Credential(
            OperatorPrincipal principal,
            String key,
            byte[] keyBytes
    ) {
    }
}
