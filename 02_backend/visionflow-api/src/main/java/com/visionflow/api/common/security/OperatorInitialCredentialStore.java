package com.visionflow.api.common.security;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.nio.file.StandardCopyOption;
import java.nio.file.attribute.PosixFilePermission;
import java.nio.file.attribute.PosixFilePermissions;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;

@Component
public class OperatorInitialCredentialStore {

    private static final Logger log = LoggerFactory.getLogger(
            OperatorInitialCredentialStore.class
    );
    private static final Set<PosixFilePermission> OWNER_ONLY = Set.of(
            PosixFilePermission.OWNER_READ,
            PosixFilePermission.OWNER_WRITE
    );

    private final Path credentialFile;

    public OperatorInitialCredentialStore(
            @Value("${VISIONFLOW_OPERATOR_BOOTSTRAP_CREDENTIAL_FILE:/app/data/operator-bootstrap/initial-credentials.txt}")
            String credentialFile
    ) {
        this.credentialFile = Path.of(credentialFile).toAbsolutePath().normalize();
    }

    public synchronized void writeInitialCredentials(
            List<InitialCredential> credentials
    ) {
        if (credentials == null || credentials.isEmpty()) {
            throw new IllegalArgumentException("초기 운영자 계정 정보가 필요합니다.");
        }

        List<String> lines = new ArrayList<>();
        lines.add("# VisionFlow one-time operator credentials");
        lines.add("# Format: username<TAB>role<TAB>temporary-password");
        lines.add("# Change each password immediately after first login.");
        for (InitialCredential credential : credentials) {
            lines.add(
                    credential.username()
                            + "\t"
                            + credential.role().name()
                            + "\t"
                            + credential.password()
            );
        }
        writeAtomically(lines);
    }

    public synchronized void removeCredential(String username) {
        if (username == null || username.isBlank() || !Files.exists(credentialFile)) {
            return;
        }
        try {
            List<String> lines = Files.readAllLines(
                    credentialFile,
                    StandardCharsets.UTF_8
            );
            String normalized = username.trim();
            List<String> remaining = lines.stream()
                    .filter(line -> !credentialUsername(line).equalsIgnoreCase(normalized))
                    .toList();
            boolean hasCredentials = remaining.stream()
                    .anyMatch(line -> !credentialUsername(line).isEmpty());
            if (!hasCredentials) {
                Files.deleteIfExists(credentialFile);
                return;
            }
            writeAtomically(remaining);
        } catch (IOException error) {
            log.warn(
                    "초기 운영자 자격증명 파일 정리에 실패했습니다: path={}",
                    credentialFile,
                    error
            );
        }
    }

    public synchronized void deleteFile() {
        try {
            Files.deleteIfExists(credentialFile);
        } catch (IOException error) {
            log.warn(
                    "초기 운영자 자격증명 파일 삭제에 실패했습니다: path={}",
                    credentialFile,
                    error
            );
        }
    }

    Path credentialFile() {
        return credentialFile;
    }

    private void writeAtomically(List<String> lines) {
        Path temporary = null;
        try {
            Path parent = credentialFile.getParent();
            if (parent == null) {
                throw new IOException("초기 운영자 자격증명 디렉터리가 없습니다.");
            }

            Files.createDirectories(parent);
            String prefix = credentialFile.getFileName() + ".";
            try {
                temporary = Files.createTempFile(
                        parent,
                        prefix,
                        ".tmp",
                        PosixFilePermissions.asFileAttribute(OWNER_ONLY)
                );
            } catch (UnsupportedOperationException ignored) {
                temporary = Files.createTempFile(parent, prefix, ".tmp");
                restrictPermissions(temporary);
            }
            Files.write(
                    temporary,
                    lines,
                    StandardCharsets.UTF_8,
                    StandardOpenOption.WRITE,
                    StandardOpenOption.TRUNCATE_EXISTING,
                    LinkOption.NOFOLLOW_LINKS
            );
            restrictPermissions(temporary);
            try {
                Files.move(
                        temporary,
                        credentialFile,
                        StandardCopyOption.ATOMIC_MOVE,
                        StandardCopyOption.REPLACE_EXISTING
                );
            } catch (AtomicMoveNotSupportedException ignored) {
                Files.move(
                        temporary,
                        credentialFile,
                        StandardCopyOption.REPLACE_EXISTING
                );
            }
            restrictPermissions(credentialFile);
        } catch (IOException error) {
            throw new IllegalStateException(
                    "초기 운영자 자격증명 파일을 안전하게 저장할 수 없습니다.",
                    error
            );
        } finally {
            if (temporary != null) {
                try {
                    Files.deleteIfExists(temporary);
                } catch (IOException error) {
                    log.warn("초기 운영자 임시 자격증명 파일 삭제에 실패했습니다", error);
                }
            }
        }
    }

    private void restrictPermissions(Path path) {
        try {
            Files.setPosixFilePermissions(path, OWNER_ONLY);
        } catch (UnsupportedOperationException | IOException ignored) {
            // Docker Desktop bind mounts may not expose POSIX permissions.
        }
    }

    private String credentialUsername(String line) {
        if (line == null || line.isBlank() || line.startsWith("#")) {
            return "";
        }
        int separator = line.indexOf('\t');
        return separator < 0 ? "" : line.substring(0, separator).trim();
    }

    public record InitialCredential(
            String username,
            OperatorRole role,
            String password
    ) {
    }
}
