package com.visionflow.api.ai.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.PrePersist;
import jakarta.persistence.PreUpdate;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;

import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;

@Entity
@Table(
        name = "ai_phase3_event",
        uniqueConstraints = @UniqueConstraint(
                name = "uk_ai_phase3_event_key",
                columnNames = "event_key"
        )
)
public class AiPhase3Event {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "event_key", nullable = false, length = 200)
    private String eventKey;

    @Column(name = "source_id", nullable = false, length = 100)
    private String sourceId;

    @Column(name = "session_id", nullable = false, length = 36)
    private String sessionId;

    @Enumerated(jakarta.persistence.EnumType.STRING)
    @Column(name = "source_type", nullable = false, length = 30)
    private VideoSourceType sourceType;

    @Column(name = "drone_id", nullable = false)
    private Long droneId;

    @Column(name = "track_id", nullable = false)
    private Long trackId;

    @Column(name = "frame_index", nullable = false)
    private Long frameIndex;

    @Column(name = "captured_at", nullable = false)
    private LocalDateTime capturedAt;

    @Column(name = "ppe_state", nullable = false, length = 40)
    private String ppeState;

    @Column(name = "no_helmet_rate", nullable = false, precision = 8, scale = 6)
    private BigDecimal noHelmetRate;

    @Column(name = "helmet_rate", nullable = false, precision = 8, scale = 6)
    private BigDecimal helmetRate;

    @Column(name = "unknown_rate", nullable = false, precision = 8, scale = 6)
    private BigDecimal unknownRate;

    @Column(name = "streak_seconds", nullable = false, precision = 12, scale = 3)
    private BigDecimal streakSeconds;

    @Column(name = "estimated_depth_m", precision = 12, scale = 3)
    private BigDecimal estimatedDepthM;

    @Column(name = "scene_q33_m", precision = 12, scale = 3)
    private BigDecimal sceneQ33M;

    @Column(name = "scene_q66_m", precision = 12, scale = 3)
    private BigDecimal sceneQ66M;

    @Column(name = "depth_bucket", length = 20)
    private String depthBucket;

    @Column(name = "enrichment_latency_ms", precision = 12, scale = 2)
    private BigDecimal enrichmentLatencyMs;

    @Column(name = "created_at", nullable = false)
    private LocalDateTime createdAt;

    @Column(name = "updated_at", nullable = false)
    private LocalDateTime updatedAt;

    protected AiPhase3Event() {
    }

    public static AiPhase3Event create(
            String eventKey,
            String sourceId,
            String sessionId,
            VideoSourceType sourceType,
            Long droneId,
            Long trackId,
            Long frameIndex,
            Instant capturedAt,
            String ppeState,
            BigDecimal noHelmetRate,
            BigDecimal helmetRate,
            BigDecimal unknownRate,
            BigDecimal streakSeconds
    ) {
        AiPhase3Event event = new AiPhase3Event();
        event.eventKey = eventKey;
        event.sourceId = sourceId;
        event.sessionId = sessionId;
        event.sourceType = sourceType;
        event.droneId = droneId;
        event.trackId = trackId;
        event.frameIndex = frameIndex;
        event.capturedAt = LocalDateTime.ofInstant(capturedAt, ZoneOffset.UTC);
        event.ppeState = ppeState;
        event.noHelmetRate = noHelmetRate;
        event.helmetRate = helmetRate;
        event.unknownRate = unknownRate;
        event.streakSeconds = streakSeconds;
        return event;
    }

    public void enrichDepth(
            BigDecimal estimatedDepthM,
            BigDecimal sceneQ33M,
            BigDecimal sceneQ66M,
            String depthBucket,
            BigDecimal enrichmentLatencyMs
    ) {
        this.estimatedDepthM = estimatedDepthM;
        this.sceneQ33M = sceneQ33M;
        this.sceneQ66M = sceneQ66M;
        this.depthBucket = depthBucket;
        this.enrichmentLatencyMs = enrichmentLatencyMs;
    }

    @PrePersist
    void prePersist() {
        LocalDateTime now = LocalDateTime.now(ZoneOffset.UTC);

        if (createdAt == null) {
            createdAt = now;
        }

        updatedAt = now;
    }

    @PreUpdate
    void preUpdate() {
        updatedAt = LocalDateTime.now(ZoneOffset.UTC);
    }

    public Long getId() {
        return id;
    }

    public String getEventKey() {
        return eventKey;
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

    public Long getTrackId() {
        return trackId;
    }

    public Long getFrameIndex() {
        return frameIndex;
    }

    public LocalDateTime getCapturedAt() {
        return capturedAt;
    }

    public String getPpeState() {
        return ppeState;
    }

    public BigDecimal getNoHelmetRate() {
        return noHelmetRate;
    }

    public BigDecimal getHelmetRate() {
        return helmetRate;
    }

    public BigDecimal getUnknownRate() {
        return unknownRate;
    }

    public BigDecimal getStreakSeconds() {
        return streakSeconds;
    }

    public BigDecimal getEstimatedDepthM() {
        return estimatedDepthM;
    }

    public BigDecimal getSceneQ33M() {
        return sceneQ33M;
    }

    public BigDecimal getSceneQ66M() {
        return sceneQ66M;
    }

    public String getDepthBucket() {
        return depthBucket;
    }

    public BigDecimal getEnrichmentLatencyMs() {
        return enrichmentLatencyMs;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }

    public LocalDateTime getUpdatedAt() {
        return updatedAt;
    }
}
