package com.visionflow.api.common.security;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class AiInternalCredentialRegistryTests {

    private static final String VALID_KEY =
            "stage2-test-ai-internal-key-0123456789abcdef";

    @Test
    void enabledRegistryMatchesOnlyConfiguredKey() {
        AiInternalCredentialRegistry registry =
                new AiInternalCredentialRegistry(true, VALID_KEY);

        assertThat(registry.isEnabled()).isTrue();
        assertThat(registry.matches(VALID_KEY)).isTrue();
        assertThat(registry.matches("wrong-key")).isFalse();
        assertThat(registry.matches(null)).isFalse();
    }

    @Test
    void disabledRegistryDoesNotRequireKey() {
        AiInternalCredentialRegistry registry =
                new AiInternalCredentialRegistry(false, "");

        assertThat(registry.isEnabled()).isFalse();
        assertThat(registry.matches(VALID_KEY)).isFalse();
    }

    @Test
    void enabledRegistryRequiresAtLeast32Characters() {
        assertThatThrownBy(
                () -> new AiInternalCredentialRegistry(true, "too-short")
        )
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("32");
    }
}
