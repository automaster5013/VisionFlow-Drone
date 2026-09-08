package com.visionflow.api.flight.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Index;
import jakarta.persistence.PrePersist;
import jakarta.persistence.PreUpdate;
import jakarta.persistence.Table;

import java.time.LocalDateTime;

@Entity
@Table(
        name = "flight_session",
        indexes = {
                @Index(
                        name = "idx_flight_session_drone_started",
                        columnList = "drone_id, started_at"
                ),
                @Index(
                        name = "idx_flight_session_drone_status",
                        columnList = "drone_id, status"
                )
        }
)
public class FlightSession {

    @Id
    @Column(name = "session_id", length = 36, nullable = false)
    private String sessionId;

    @Column(name = "drone_id", nullable = false)
    private Long droneId;

    @Column(name = "name", length = 120, nullable = false)
    private String name;

    @Column(name = "description", length = 500)
    private String description;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", length = 20, nullable = false)
    private FlightSessionStatus status;

    @Column(name = "source_device_id", length = 100)
    private String sourceDeviceId;

    @Column(name = "started_at", nullable = false)
    private LocalDateTime startedAt;

    @Column(name = "ended_at")
    private LocalDateTime endedAt;

    @Column(name = "created_at", nullable = false, updatable = false)
    private LocalDateTime createdAt;

    @Column(name = "updated_at", nullable = false)
    private LocalDateTime updatedAt;

    @jakarta.persistence.ElementCollection
    @jakarta.persistence.CollectionTable(name = "flight_session_pause", joinColumns = @jakarta.persistence.JoinColumn(name = "session_id"))
    @jakarta.persistence.OrderColumn(name = "pause_index")
    private java.util.List<FlightSessionPause> pauses = new java.util.ArrayList<>();

    public java.util.List<FlightSessionPause> getPauses() { return java.util.List.copyOf(pauses); }

    public void pause(LocalDateTime at) {
        requirePresentationSession();
        if (!pauses.isEmpty() && pauses.get(pauses.size() - 1).getResumedAt() == null) return;
        if (pauses.size() >= 1000) throw new IllegalArgumentException("일시정지 기록 한도에 도달했습니다.");
        pauses.add(new FlightSessionPause(normalizeEndedAt(at)));
        touch();
    }

    public void resume(LocalDateTime at) {
        requirePresentationSession();
        closePause(at);
        touch();
    }

    private void closePause(LocalDateTime at) {
        if (!pauses.isEmpty()) pauses.get(pauses.size() - 1).resume(at);
    }

    private void requirePresentationSession() {
        if (status != FlightSessionStatus.ACTIVE || !"presentation-simulator-001".equals(sourceDeviceId)) {
            throw new IllegalArgumentException("진행 중인 발표 시연 세션만 일시정지·재개할 수 있습니다.");
        }
    }

    protected FlightSession() {
    }

    private FlightSession(
            String sessionId,
            Long droneId,
            String name,
            String description,
            String sourceDeviceId,
            LocalDateTime startedAt
    ) {
        this.sessionId = sessionId;
        this.droneId = droneId;
        this.name = name;
        this.description = description;
        this.status = FlightSessionStatus.ACTIVE;
        this.sourceDeviceId = sourceDeviceId;
        this.startedAt = startedAt;
        this.createdAt = startedAt;
        this.updatedAt = startedAt;
    }

    public static FlightSession start(
            String sessionId,
            Long droneId,
            String name,
            String description,
            String sourceDeviceId,
            LocalDateTime startedAt
    ) {
        return new FlightSession(
                sessionId,
                droneId,
                name,
                description,
                sourceDeviceId,
                startedAt
        );
    }

    public void rename(String nextName) {
        this.name = nextName;
        touch();
    }

    public void changeDescription(String nextDescription) {
        this.description = nextDescription;
        touch();
    }

    public void complete(LocalDateTime completedAt) {
        if (status == FlightSessionStatus.COMPLETED) {
            return;
        }

        ensureOpen(FlightSessionStatus.COMPLETED);
        this.status = FlightSessionStatus.COMPLETED;
        this.endedAt = normalizeEndedAt(completedAt);
        closePause(this.endedAt);
        touch();
    }

    public void abort(LocalDateTime abortedAt) {
        if (status == FlightSessionStatus.ABORTED) {
            return;
        }

        ensureOpen(FlightSessionStatus.ABORTED);
        this.status = FlightSessionStatus.ABORTED;
        this.endedAt = normalizeEndedAt(abortedAt);
        closePause(this.endedAt);
        touch();
    }

    private void ensureOpen(FlightSessionStatus targetStatus) {
        if (status.isTerminal()) {
            throw new IllegalArgumentException(
                    "종료된 비행 세션은 "
                            + targetStatus.name()
                            + " 상태로 변경할 수 없습니다."
            );
        }
    }

    private LocalDateTime normalizeEndedAt(LocalDateTime value) {
        return value.isBefore(startedAt) ? startedAt : value;
    }

    private void touch() {
        this.updatedAt = LocalDateTime.now();
    }

    @PrePersist
    private void prePersist() {
        LocalDateTime now = LocalDateTime.now();

        if (startedAt == null) {
            startedAt = now;
        }

        if (createdAt == null) {
            createdAt = now;
        }

        if (updatedAt == null) {
            updatedAt = now;
        }

        if (status == null) {
            status = FlightSessionStatus.READY;
        }
    }

    @PreUpdate
    private void preUpdate() {
        updatedAt = LocalDateTime.now();
    }

    public String getSessionId() {
        return sessionId;
    }

    public Long getDroneId() {
        return droneId;
    }

    public String getName() {
        return name;
    }

    public String getDescription() {
        return description;
    }

    public FlightSessionStatus getStatus() {
        return status;
    }

    public String getSourceDeviceId() {
        return sourceDeviceId;
    }

    public LocalDateTime getStartedAt() {
        return startedAt;
    }

    public LocalDateTime getEndedAt() {
        return endedAt;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }

    public LocalDateTime getUpdatedAt() {
        return updatedAt;
    }
}
