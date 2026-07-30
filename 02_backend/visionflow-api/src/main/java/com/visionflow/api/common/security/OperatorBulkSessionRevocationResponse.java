package com.visionflow.api.common.security;

public record OperatorBulkSessionRevocationResponse(
        int revokedCount,
        boolean currentSessionPreserved
) {
}
