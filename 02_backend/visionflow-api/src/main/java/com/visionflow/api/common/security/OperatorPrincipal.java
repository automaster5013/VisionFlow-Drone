package com.visionflow.api.common.security;

public record OperatorPrincipal(
        String username,
        OperatorRole role,
        boolean passwordChangeRequired
) {
    public OperatorPrincipal(
            String username,
            OperatorRole role
    ) {
        this(username, role, false);
    }
}
