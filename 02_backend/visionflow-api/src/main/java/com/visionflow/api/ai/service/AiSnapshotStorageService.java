package com.visionflow.api.ai.service;

import com.visionflow.api.common.exception.ResourceNotFoundException;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;

import java.io.IOException;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.UUID;

@Service
public class AiSnapshotStorageService {

    private static final String JPEG_CONTENT_TYPE = "image/jpeg";
    private static final long MAX_FILE_SIZE_BYTES = 10L * 1024L * 1024L;

    private final Path storageRoot;

    public AiSnapshotStorageService(
            @Value("${visionflow.ai.snapshot.storage-path:./data/ai-snapshots}")
            String storagePath
    ) {
        this.storageRoot = Path.of(storagePath)
                .toAbsolutePath()
                .normalize();
    }

    public StoredSnapshot store(
            Long eventId,
            MultipartFile file
    ) {
        byte[] bytes = validateAndRead(file);
        String fileName = "event-" + eventId + ".jpg";
        Path target = resolveSafely(fileName);
        Path temporary = resolveSafely(
                ".event-" + eventId + "-" + UUID.randomUUID() + ".tmp"
        );

        try {
            Files.createDirectories(storageRoot);
            Files.write(temporary, bytes);

            try {
                Files.move(
                        temporary,
                        target,
                        StandardCopyOption.ATOMIC_MOVE,
                        StandardCopyOption.REPLACE_EXISTING
                );
            } catch (AtomicMoveNotSupportedException ignored) {
                Files.move(
                        temporary,
                        target,
                        StandardCopyOption.REPLACE_EXISTING
                );
            }

            return new StoredSnapshot(
                    fileName,
                    JPEG_CONTENT_TYPE,
                    bytes.length
            );
        } catch (IOException error) {
            tryDelete(temporary);

            throw new ResponseStatusException(
                    HttpStatus.INTERNAL_SERVER_ERROR,
                    "AI 이벤트 스냅샷 저장에 실패했습니다.",
                    error
            );
        }
    }

    public Resource load(String fileName) {
        Path path = resolveSafely(fileName);
        Resource resource = new FileSystemResource(path);

        if (!resource.exists() || !resource.isReadable()) {
            throw new ResourceNotFoundException(
                    "AI 이벤트 스냅샷 파일을 찾을 수 없습니다."
            );
        }

        return resource;
    }

    private byte[] validateAndRead(MultipartFile file) {
        if (file == null || file.isEmpty()) {
            throw badRequest("비어 있는 스냅샷 파일은 저장할 수 없습니다.");
        }

        if (file.getSize() > MAX_FILE_SIZE_BYTES) {
            throw badRequest("스냅샷 파일은 10MB 이하여야 합니다.");
        }

        try {
            byte[] bytes = file.getBytes();

            if (!isJpeg(bytes)) {
                throw badRequest("JPEG 형식의 스냅샷만 저장할 수 있습니다.");
            }

            return bytes;
        } catch (IOException error) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "스냅샷 파일을 읽을 수 없습니다.",
                    error
            );
        }
    }

    private boolean isJpeg(byte[] bytes) {
        return bytes.length >= 4
                && (bytes[0] & 0xFF) == 0xFF
                && (bytes[1] & 0xFF) == 0xD8
                && (bytes[bytes.length - 2] & 0xFF) == 0xFF
                && (bytes[bytes.length - 1] & 0xFF) == 0xD9;
    }

    private Path resolveSafely(String fileName) {
        Path path = storageRoot.resolve(fileName).normalize();

        if (!path.startsWith(storageRoot)) {
            throw badRequest("잘못된 스냅샷 파일 경로입니다.");
        }

        return path;
    }

    private ResponseStatusException badRequest(String message) {
        return new ResponseStatusException(HttpStatus.BAD_REQUEST, message);
    }

    private void tryDelete(Path path) {
        try {
            Files.deleteIfExists(path);
        } catch (IOException ignored) {
            // 원래 저장 예외를 유지합니다.
        }
    }

    public record StoredSnapshot(
            String fileName,
            String contentType,
            long sizeBytes
    ) {
    }
}
