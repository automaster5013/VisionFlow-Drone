package com.visionflow.api.demo.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.PrePersist;
import jakarta.persistence.PreUpdate;
import jakarta.persistence.Table;

import java.time.LocalDateTime;
import java.time.ZoneOffset;

@Entity
@Table(name = "demo_scenario")
public class DemoScenario {

    @Id
    @Column(name = "scenario_id", nullable = false, length = 36)
    private String scenarioId;

    @Column(name = "drone_id", nullable = false)
    private Long droneId;

    @Column(name = "flight_session_id", nullable = false, length = 36)
    private String flightSessionId;

    @Column(name = "ai_event_id")
    private Long aiEventId;

    @Column(name = "ai_alert_id")
    private Long aiAlertId;

    @Column(name = "incident_id")
    private Long incidentId;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private DemoScenarioStage stage;

    @Column(name = "last_message", nullable = false, length = 500)
    private String lastMessage;

    @Column(name = "started_at", nullable = false)
    private LocalDateTime startedAt;

    @Column(name = "updated_at", nullable = false)
    private LocalDateTime updatedAt;

    @Column(name = "completed_at")
    private LocalDateTime completedAt;

    protected DemoScenario() {
    }

    public static DemoScenario start(
            String scenarioId,
            Long droneId,
            String flightSessionId
    ) {
        DemoScenario scenario = new DemoScenario();
        scenario.scenarioId = scenarioId;
        scenario.droneId = droneId;
        scenario.flightSessionId = flightSessionId;
        scenario.stage = DemoScenarioStage.READY;
        scenario.lastMessage = "비행 세션과 시연 경로가 준비되었습니다.";
        scenario.startedAt = LocalDateTime.now(ZoneOffset.UTC);
        return scenario;
    }

    public void markDetected(
            Long aiEventId,
            Long aiAlertId,
            Long incidentId
    ) {
        requireStage(DemoScenarioStage.READY);
        this.aiEventId = aiEventId;
        this.aiAlertId = aiAlertId;
        this.incidentId = incidentId;
        this.stage = DemoScenarioStage.DETECTED;
        this.lastMessage = "화재 객체를 탐지하고 Incident를 생성했습니다.";
    }

    public void markEscalated() {
        requireStage(DemoScenarioStage.DETECTED);
        this.stage = DemoScenarioStage.ESCALATED;
        this.lastMessage = "SLA 초과를 재현하고 에스컬레이션 Lv.1을 기록했습니다.";
    }

    public void markResolved() {
        requireStage(DemoScenarioStage.ESCALATED);
        this.stage = DemoScenarioStage.RESOLVED;
        this.lastMessage = "관제 담당자가 AI 경보와 Incident를 해결했습니다.";
    }

    public void markCompleted() {
        requireStage(DemoScenarioStage.RESOLVED);
        this.stage = DemoScenarioStage.COMPLETED;
        this.lastMessage = "비행 세션을 종료하고 보고서 생성 준비를 마쳤습니다.";
        this.completedAt = LocalDateTime.now(ZoneOffset.UTC);
    }

    private void requireStage(DemoScenarioStage expected) {
        if (stage != expected) {
            throw new IllegalArgumentException(
                    "현재 시연 단계에서는 실행할 수 없습니다. expected="
                            + expected
                            + ", actual="
                            + stage
            );
        }
    }

    @PrePersist
    void prePersist() {
        LocalDateTime now = LocalDateTime.now(ZoneOffset.UTC);
        if (startedAt == null) {
            startedAt = now;
        }
        updatedAt = now;
    }

    @PreUpdate
    void preUpdate() {
        updatedAt = LocalDateTime.now(ZoneOffset.UTC);
    }

    public String getScenarioId() {
        return scenarioId;
    }

    public Long getDroneId() {
        return droneId;
    }

    public String getFlightSessionId() {
        return flightSessionId;
    }

    public Long getAiEventId() {
        return aiEventId;
    }

    public Long getAiAlertId() {
        return aiAlertId;
    }

    public Long getIncidentId() {
        return incidentId;
    }

    public DemoScenarioStage getStage() {
        return stage;
    }

    public String getLastMessage() {
        return lastMessage;
    }

    public LocalDateTime getStartedAt() {
        return startedAt;
    }

    public LocalDateTime getUpdatedAt() {
        return updatedAt;
    }

    public LocalDateTime getCompletedAt() {
        return completedAt;
    }
}
