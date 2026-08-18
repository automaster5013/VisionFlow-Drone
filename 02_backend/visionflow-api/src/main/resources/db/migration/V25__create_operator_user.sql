CREATE TABLE operator_user (
    id BIGINT NOT NULL AUTO_INCREMENT,
    username VARCHAR(100) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    last_login_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,

    PRIMARY KEY (id),
    UNIQUE KEY uk_operator_user_username (username),
    KEY idx_operator_user_role_enabled (role, enabled),

    CONSTRAINT chk_operator_user_role
        CHECK (role IN ('VIEWER', 'OPERATOR', 'ADMIN'))
);
