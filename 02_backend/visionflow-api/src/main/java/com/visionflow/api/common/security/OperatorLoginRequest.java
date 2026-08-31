package com.visionflow.api.common.security;

import jakarta.validation.constraints.Size;

public record OperatorLoginRequest(
        @Size(max = 100)
        String username,

        @Size(max = 4096)
        String password
) {
}
