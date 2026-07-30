package com.visionflow.api.common.security;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class OperatorCredentialRegistryTests {

    private static final String VIEWER_KEY = "viewer-key-12345678901234567890";
    private static final String OPERATOR_KEY = "operator-key-123456789012345678";
    private static final String ADMIN_KEY = "admin-key-123456789012345678901";

    @Test
    void disabledRegistryDoesNotRequireCredentials() {
        OperatorCredentialRegistry registry = registry(
                false,
                "",
                "",
                ""
        );

        assertThat(registry.isEnabled()).isFalse();
        assertThat(registry.resolve(VIEWER_KEY)).isEmpty();
    }

    @Test
    void resolvesConfiguredRolesWhenEnabled() {
        OperatorCredentialRegistry registry = registry(
                true,
                VIEWER_KEY,
                OPERATOR_KEY,
                ADMIN_KEY
        );

        assertThat(registry.resolve(VIEWER_KEY))
                .contains(new OperatorPrincipal("viewer", OperatorRole.VIEWER));
        assertThat(registry.resolve(OPERATOR_KEY))
                .contains(new OperatorPrincipal("operator", OperatorRole.OPERATOR));
        assertThat(registry.resolve(ADMIN_KEY))
                .contains(new OperatorPrincipal("admin", OperatorRole.ADMIN));
        assertThat(registry.resolve("not-configured-key-1234567890")).isEmpty();
    }

    @Test
    void enabledRegistryRequiresAtLeastOneCredential() {
        assertThatThrownBy(() -> registry(true, "", "", ""))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("하나 이상");
    }

    @Test
    void rejectsDuplicatedCredentials() {
        assertThatThrownBy(() -> registry(true, VIEWER_KEY, VIEWER_KEY, ""))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("서로 달라야");
    }

    private OperatorCredentialRegistry registry(
            boolean enabled,
            String viewerKey,
            String operatorKey,
            String adminKey
    ) {
        return new OperatorCredentialRegistry(
                enabled,
                "viewer",
                viewerKey,
                "operator",
                operatorKey,
                "admin",
                adminKey
        );
    }
}
