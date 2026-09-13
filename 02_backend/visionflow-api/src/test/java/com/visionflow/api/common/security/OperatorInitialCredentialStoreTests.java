package com.visionflow.api.common.security;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import org.junit.jupiter.api.Assumptions;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

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

    @Test
    void doesNotFollowPredictableTemporaryFileSymlink() throws Exception {
        Path file = tempDir.resolve("initial-credentials.txt");
        Path sentinel = tempDir.resolve("sentinel.txt");
        Path plantedLink = tempDir.resolve("initial-credentials.txt.tmp");
        Files.writeString(sentinel, "must remain untouched");
        try {
            Files.createSymbolicLink(plantedLink, sentinel);
        } catch (
                UnsupportedOperationException | SecurityException | IOException error
        ) {
            Assumptions.assumeTrue(false, "Symbolic links are unavailable here");
        }

        OperatorInitialCredentialStore store =
                new OperatorInitialCredentialStore(file.toString());
        store.writeInitialCredentials(
                List.of(
                        new OperatorInitialCredentialStore.InitialCredential(
                                "operator",
                                OperatorRole.OPERATOR,
                                "temporary-password"
                        )
                )
        );

        assertThat(Files.readString(sentinel)).isEqualTo("must remain untouched");
        assertThat(Files.readString(file)).contains("temporary-password");
    }
}
