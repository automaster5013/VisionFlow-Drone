package com.visionflow.api.common.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

@Configuration
public class OperatorPasswordConfig {

    private static final int BCRYPT_STRENGTH = 12;

    @Bean
    public PasswordEncoder operatorPasswordEncoder() {
        return new BCryptPasswordEncoder(BCRYPT_STRENGTH);
    }
}
