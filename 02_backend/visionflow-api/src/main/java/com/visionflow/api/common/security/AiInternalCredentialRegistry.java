package com.visionflow.api.common.security;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;

@Component
public class AiInternalCredentialRegistry {

    private static final int MINIMUM_KEY_LENGTH = 32;

    private final boolean enabled;
    private final byte[] keyBytes;

    public AiInternalCredentialRegistry(
            @Value("${visionflow.security.ai-internal.enabled:false}")
            boolean enabled,

            @Value("${visionflow.security.ai-internal.key:}")
            String key
    ) {
        this.enabled = enabled;

        String normalizedKey = key == null ? "" : key.trim();
        if (enabled && normalizedKey.length() < MINIMUM_KEY_LENGTH) {
            throw new IllegalStateException(
                    "AI 내부 서비스 인증을 활성화하려면 "
                            + "VISIONFLOW_AI_INTERNAL_KEY를 32자 이상으로 설정해야 합니다."
            );
        }

        this.keyBytes = normalizedKey.getBytes(StandardCharsets.UTF_8);
    }

    public boolean isEnabled() {
        return enabled;
    }

    public boolean matches(String presentedKey) {
        if (!enabled || presentedKey == null || presentedKey.isBlank()) {
            return false;
        }

        byte[] candidate = presentedKey.trim().getBytes(StandardCharsets.UTF_8);
        return MessageDigest.isEqual(candidate, keyBytes);
    }
}
