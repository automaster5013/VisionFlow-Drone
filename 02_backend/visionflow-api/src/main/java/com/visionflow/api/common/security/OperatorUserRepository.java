package com.visionflow.api.common.security;

import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;

public interface OperatorUserRepository extends JpaRepository<OperatorUser, Long> {

    Optional<OperatorUser> findByUsernameIgnoreCase(String username);
}
