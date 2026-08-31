package com.visionflow.api.common.security;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record OperatorPasswordChangeRequest(
        @NotBlank
        @Size(min = 15, max = 128)
        String newPassword
) {
}
