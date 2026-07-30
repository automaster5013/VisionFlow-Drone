package com.visionflow.api.common.security;

public record OperatorSecurityStatusResponse(
        boolean enabled,
        boolean authenticated,
        String username,
        String role
) {
}
