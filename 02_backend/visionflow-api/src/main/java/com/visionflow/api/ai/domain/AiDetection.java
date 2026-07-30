package com.visionflow.api.ai.domain;

import jakarta.persistence.*;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.time.ZoneOffset;

@Entity
@Table(name = "ai_detection")
public class AiDetection {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "event_id", nullable = false)
    private Long eventId;

    @Column(name = "class_id", nullable = false)
    private Integer classId;

    @Column(name = "class_name", nullable = false, length = 100)
    private String className;

    @Column(nullable = false, precision = 8, scale = 6)
    private BigDecimal confidence;

    @Column(name = "bbox_x1", nullable = false, precision = 12, scale = 3)
    private BigDecimal bboxX1;

    @Column(name = "bbox_y1", nullable = false, precision = 12, scale = 3)
    private BigDecimal bboxY1;

    @Column(name = "bbox_x2", nullable = false, precision = 12, scale = 3)
    private BigDecimal bboxX2;

    @Column(name = "bbox_y2", nullable = false, precision = 12, scale = 3)
    private BigDecimal bboxY2;

    @Column(name = "created_at", nullable = false)
    private LocalDateTime createdAt;

    protected AiDetection() {
    }

    public static AiDetection create(
            Long eventId,
            Integer classId,
            String className,
            BigDecimal confidence,
            BigDecimal bboxX1,
            BigDecimal bboxY1,
            BigDecimal bboxX2,
            BigDecimal bboxY2
    ) {
        AiDetection detection = new AiDetection();
        detection.eventId = eventId;
        detection.classId = classId;
        detection.className = className;
        detection.confidence = confidence;
        detection.bboxX1 = bboxX1;
        detection.bboxY1 = bboxY1;
        detection.bboxX2 = bboxX2;
        detection.bboxY2 = bboxY2;
        return detection;
    }

    @PrePersist
    void prePersist() {
        if (createdAt == null) {
            createdAt = LocalDateTime.now(ZoneOffset.UTC);
        }
    }

    public Long getId() {
        return id;
    }

    public Long getEventId() {
        return eventId;
    }

    public Integer getClassId() {
        return classId;
    }

    public String getClassName() {
        return className;
    }

    public BigDecimal getConfidence() {
        return confidence;
    }

    public BigDecimal getBboxX1() {
        return bboxX1;
    }

    public BigDecimal getBboxY1() {
        return bboxY1;
    }

    public BigDecimal getBboxX2() {
        return bboxX2;
    }

    public BigDecimal getBboxY2() {
        return bboxY2;
    }
}
