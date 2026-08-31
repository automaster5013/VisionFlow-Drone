package com.visionflow.api.common.security;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;

import java.security.SecureRandom;
import java.util.ArrayList;
import java.util.Base64;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

@Component
public class OperatorUserBootstrap implements ApplicationRunner {

    private static final Logger log = LoggerFactory.getLogger(
            OperatorUserBootstrap.class
    );
    private static final SecureRandom SECURE_RANDOM = new SecureRandom();
    private static final int TEMPORARY_PASSWORD_BYTES = 24;

    private final boolean securityEnabled;
    private final boolean bootstrapEnabled;
    private final OperatorUserRepository userRepository;
    private final PasswordEncoder passwordEncoder;
    private final OperatorInitialCredentialStore credentialStore;
    private final List<BootstrapAccount> accounts;

    public OperatorUserBootstrap(
            @Value("${VISIONFLOW_OPERATOR_SECURITY_ENABLED:true}")
            boolean securityEnabled,
            @Value("${VISIONFLOW_OPERATOR_ACCOUNT_BOOTSTRAP_ENABLED:false}")
            boolean bootstrapEnabled,
            OperatorUserRepository userRepository,
            PasswordEncoder passwordEncoder,
            OperatorInitialCredentialStore credentialStore,
            @Value("${VISIONFLOW_VIEWER_NAME:viewer}")
            String viewerUsername,
            @Value("${VISIONFLOW_OPERATOR_NAME:operator}")
            String operatorUsername,
            @Value("${VISIONFLOW_ADMIN_NAME:admin}")
            String adminUsername
    ) {
        this.securityEnabled = securityEnabled;
        this.bootstrapEnabled = bootstrapEnabled;
        this.userRepository = userRepository;
        this.passwordEncoder = passwordEncoder;
        this.credentialStore = credentialStore;
        this.accounts = List.of(
                new BootstrapAccount(viewerUsername, OperatorRole.VIEWER),
                new BootstrapAccount(operatorUsername, OperatorRole.OPERATOR),
                new BootstrapAccount(adminUsername, OperatorRole.ADMIN)
        );
    }

    @Override
    public void run(ApplicationArguments args) {
        if (!securityEnabled || !bootstrapEnabled || userRepository.count() > 0) {
            return;
        }

        validateUniqueUsernames();
        List<GeneratedAccount> generated = accounts.stream()
                .map(this::generate)
                .toList();
        List<OperatorInitialCredentialStore.InitialCredential> credentials =
                generated.stream()
                        .map(value -> new OperatorInitialCredentialStore.InitialCredential(
                                value.user().getUsername(),
                                value.user().getRole(),
                                value.temporaryPassword()
                        ))
                        .toList();

        credentialStore.writeInitialCredentials(credentials);
        try {
            userRepository.saveAllAndFlush(
                    generated.stream().map(GeneratedAccount::user).toList()
            );
        } catch (RuntimeException error) {
            credentialStore.deleteFile();
            throw error;
        }

        for (GeneratedAccount account : generated) {
            log.info(
                    "VISIONFLOW_OPERATOR_USER_BOOTSTRAPPED username={} role={} passwordChangeRequired=true",
                    account.user().getUsername(),
                    account.user().getRole()
            );
        }
        log.info(
                "VISIONFLOW_OPERATOR_BOOTSTRAP_CREDENTIAL_FILE_READY path={}",
                credentialStore.credentialFile()
        );
    }

    private GeneratedAccount generate(BootstrapAccount account) {
        String temporaryPassword = generateTemporaryPassword();
        OperatorUser user = OperatorUser.create(
                account.username(),
                passwordEncoder.encode(temporaryPassword),
                account.role()
        );
        return new GeneratedAccount(user, temporaryPassword);
    }

    private String generateTemporaryPassword() {
        byte[] bytes = new byte[TEMPORARY_PASSWORD_BYTES];
        SECURE_RANDOM.nextBytes(bytes);
        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(bytes);
    }

    private void validateUniqueUsernames() {
        Set<String> names = new HashSet<>();
        for (BootstrapAccount account : accounts) {
            String normalized = account.username() == null
                    ? ""
                    : account.username().trim().toLowerCase(Locale.ROOT);
            if (!names.add(normalized)) {
                throw new IllegalStateException(
                        "초기 운영자 사용자 ID는 역할별로 서로 달라야 합니다."
                );
            }
        }
    }

    private record BootstrapAccount(
            String username,
            OperatorRole role
    ) {
    }

    private record GeneratedAccount(
            OperatorUser user,
            String temporaryPassword
    ) {
    }
}
