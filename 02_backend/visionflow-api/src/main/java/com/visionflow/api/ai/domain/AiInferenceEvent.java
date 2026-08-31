package com.visionflow.api.ai.domain;

import jakarta.persistence.*;

import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;

@Entity
@Table(
        name = "ai_inference_event",
        uniqueConstraints = @UniqueConstraint(
                name = "uk_ai_event_frame",
                columnNames = {
                        "source_id",
                        "session_id",
                        "frame_index"
                }
        )
)
public class AiInferenceEvent {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "source_id", nullable = false, length = 100)
    private String sourceId;

    @Column(name = "session_id", nullable = false, length = 36)
    private String sessionId;

    @Enumerated(EnumType.STRING)
    @Column(name = "source_type", nullable = false, length = 30)
    private VideoSourceType sourceType;

    @Column(name = "drone_id", nullable = false)
    private Long droneId;

    @Column(name = "frame_index", nullable = false)
    private Long frameIndex;

    @Column(name = "captured_at", nullable = false)
    private LocalDateTime capturedAt;

    @Column(name = "received_at", nullable = false)
    private LocalDateTime receivedAt;

    @Column(name = "inference_ms", nullable = false, precision = 12, scale = 3)
    private BigDecimal inferenceMs;

    @Column(name = "detection_count", nullable = false)
    private Integer detectionCount;

    @Column(name = "snapshot_file_name", length = 255)
    private String snapshotFileName;

    @Column(name = "snapshot_content_type", length = 100)
    private String snapshotContentType;

    @Column(name = "snapshot_size_bytes")
    private Long snapshotSizeBytes;

    @Column(name = "snapshot_created_at")
    private LocalDateTime snapshotCreatedAt;

    @Column(name = "created_at", nullable = false)
    private LocalDateTime createdAt;

    protected AiInferenceEvent() {
    }

    public static AiInferenceEvent create(
            String sourceId,
            String sessionId,
            VideoSourceType sourceType,
            Long droneId,
            Long frameIndex,
            Instant capturedAt,
            BigDecimal inferenceMs,
            int detectionCount
    ) {
        AiInferenceEvent event = new AiInferenceEvent();
        event.sourceId = sourceId;
        event.sessionId = sessionId;
        event.sourceType = sourceType;
        event.droneId = droneId;
        event.frameIndex = frameIndex;
        event.capturedAt = LocalDateTime.ofInstant(
                capturedAt,
                ZoneOffset.UTC
        );
        event.receivedAt = LocalDateTime.now(ZoneOffset.UTC);
        event.inferenceMs = inferenceMs;
        event.detectionCount = detectionCount;
        return event;
    }

    @PrePersist
    void prePersist() {
        if (createdAt == null) {
            createdAt = LocalDateTime.now(ZoneOffset.UTC);
        }
    }

    public void attachSnapshot(
            String fileName,
            String contentType,
            long sizeBytes
    ) {
        this.snapshotFileName = fileName;
        this.snapshotContentType = contentType;
        this.snapshotSizeBytes = sizeBytes;
        this.snapshotCreatedAt = LocalDateTime.now(ZoneOffset.UTC);
    }

    public void clearSnapshot() {
        this.snapshotFileName = null;
        this.snapshotContentType = null;
        this.snapshotSizeBytes = null;
        this.snapshotCreatedAt = null;
    }

    public Long getId() {
        return id;
    }

    public String getSourceId() {
        return sourceId;
    }

    public String getSessionId() {
        return sessionId;
    }

    public VideoSourceType getSourceType() {
        return sourceType;
    }

    public Long getDroneId() {
        return droneId;
    }

    public Long getFrameIndex() {
        return frameIndex;
    }

    public LocalDateTime getCapturedAt() {
        return capturedAt;
    }

    public LocalDateTime getReceivedAt() {
        return receivedAt;
    }

    public BigDecimal getInferenceMs() {
        return inferenceMs;
    }

    public Integer getDetectionCount() {
        return detectionCount;
    }

    public String getSnapshotFileName() {
        return snapshotFileName;
    }

    public String getSnapshotContentType() {
        return snapshotContentType;
    }

    public Long getSnapshotSizeBytes() {
        return snapshotSizeBytes;
    }

    public LocalDateTime getSnapshotCreatedAt() {
        return snapshotCreatedAt;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }
}
