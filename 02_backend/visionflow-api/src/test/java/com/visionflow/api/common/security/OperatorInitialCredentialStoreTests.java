package com.visionflow.api.common.security;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

class OperatorInitialCredentialStoreTests {

    @TempDir
    Path tempDir;

    @Test
    void removesRotatedCredentialsAndDeletesFileWhenEmpty() throws Exception {
        Path file = tempDir.resolve("initial-credentials.txt");
        OperatorInitialCredentialStore store =
                new OperatorInitialCredentialStore(file.toString());

        store.writeInitialCredentials(
                List.of(
                        new OperatorInitialCredentialStore.InitialCredential(
                                "viewer",
                                OperatorRole.VIEWER,
                                "viewer-temp-password"
                        ),
                        new OperatorInitialCredentialStore.InitialCredential(
                                "operator",
                                OperatorRole.OPERATOR,
                                "operator-temp-password"
                        )
                )
        );

        assertThat(Files.readString(file)).contains("viewer-temp-password");
        store.removeCredential("viewer");
        assertThat(Files.readString(file))
                .doesNotContain("viewer-temp-password")
                .contains("operator-temp-password");

        store.removeCredential("operator");
        assertThat(file).doesNotExist();
    }
}
