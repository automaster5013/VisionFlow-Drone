package com.visionflow.api.common.security;

public enum OperatorRole {
    VIEWER,
    OPERATOR,
    ADMIN;

    public String authority() {
        return "ROLE_" + name();
    }
}
