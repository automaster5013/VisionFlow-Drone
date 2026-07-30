package com.visionflow.api.common.security;

public record OperatorPrincipal(
        String username,
        OperatorRole role
) {
}
