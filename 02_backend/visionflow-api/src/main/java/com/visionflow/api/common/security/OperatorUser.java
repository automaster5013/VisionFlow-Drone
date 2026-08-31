package com.visionflow.api.common.security;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.PrePersist;
import jakarta.persistence.PreUpdate;
import jakarta.persistence.Table;

import java.time.LocalDateTime;
import java.time.ZoneOffset;

@Entity
@Table(name = "operator_user")
public class OperatorUser {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "username", nullable = false, length = 100, unique = true)
    private String username;

    @Column(name = "password_hash", nullable = false, length = 255)
    private String passwordHash;

    @Enumerated(EnumType.STRING)
    @Column(name = "role", nullable = false, length = 20)
    private OperatorRole role;

    @Column(name = "enabled", nullable = false)
    private boolean enabled;

    @Column(name = "must_change_password", nullable = false)
    private boolean passwordChangeRequired;

    @Column(name = "last_login_at")
    private LocalDateTime lastLoginAt;

    @Column(name = "created_at", nullable = false)
    private LocalDateTime createdAt;

    @Column(name = "updated_at", nullable = false)
    private LocalDateTime updatedAt;

    protected OperatorUser() {
    }

    private OperatorUser(
            String username,
            String passwordHash,
            OperatorRole role
    ) {
        this.username = normalizeUsername(username);
        this.passwordHash = requirePasswordHash(passwordHash);
        this.role = requireRole(role);
        this.enabled = true;
        this.passwordChangeRequired = true;
    }

    public static OperatorUser create(
            String username,
            String passwordHash,
            OperatorRole role
    ) {
        return new OperatorUser(username, passwordHash, role);
    }

    public Long getId() {
        return id;
    }

    public String getUsername() {
        return username;
    }

    public String getPasswordHash() {
        return passwordHash;
    }

    public OperatorRole getRole() {
        return role;
    }

    public boolean isEnabled() {
        return enabled;
    }

    public boolean isPasswordChangeRequired() {
        return passwordChangeRequired;
    }

    public LocalDateTime getLastLoginAt() {
        return lastLoginAt;
    }

    public void markLogin(LocalDateTime value) {
        lastLoginAt = value;
    }

    public void changePassword(String newPasswordHash) {
        passwordHash = requirePasswordHash(newPasswordHash);
        passwordChangeRequired = false;
    }

    @PrePersist
    void onCreate() {
        LocalDateTime now = LocalDateTime.now(ZoneOffset.UTC);
        createdAt = now;
        updatedAt = now;
    }

    @PreUpdate
    void onUpdate() {
        updatedAt = LocalDateTime.now(ZoneOffset.UTC);
    }

    private static String normalizeUsername(String value) {
        String normalized = value == null ? "" : value.trim();
        if (
                normalized.isEmpty()
                        || normalized.length() > 100
                        || normalized.chars().anyMatch(Character::isISOControl)
        ) {
            throw new IllegalArgumentException("운영자 사용자 ID 형식이 올바르지 않습니다.");
        }
        return normalized;
    }

    private static String requirePasswordHash(String value) {
        if (value == null || value.isBlank() || value.length() > 255) {
            throw new IllegalArgumentException("운영자 비밀번호 해시가 올바르지 않습니다.");
        }
        return value;
    }

    private static OperatorRole requireRole(OperatorRole value) {
        if (value == null) {
            throw new IllegalArgumentException("운영자 역할이 필요합니다.");
        }
        return value;
    }
}
