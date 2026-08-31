package com.visionflow.api.ai.service;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.assertj.core.api.Assertions.assertThat;

class AiSnapshotStorageServiceDeletionTests {
    @TempDir
    Path tempDir;

    @Test
    void deleteRemovesSnapshotAndIsIdempotentWhenFileIsAlreadyGone() throws Exception {
        Path snapshot = tempDir.resolve("event-77.jpg");
        Files.write(snapshot, new byte[]{1, 2, 3});
        AiSnapshotStorageService service = new AiSnapshotStorageService(tempDir.toString());

        assertThat(service.delete("event-77.jpg")).isTrue();
        assertThat(Files.exists(snapshot)).isFalse();
        assertThat(service.delete("event-77.jpg")).isFalse();
    }
}
