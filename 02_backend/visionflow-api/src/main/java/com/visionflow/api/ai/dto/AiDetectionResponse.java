package com.visionflow.api.ai.dto;

import com.visionflow.api.ai.domain.AiDetection;

import java.math.BigDecimal;

public record AiDetectionResponse(
        Long id,
        Integer classId,
        String className,
        BigDecimal confidence,
        BigDecimal x1,
        BigDecimal y1,
        BigDecimal x2,
        BigDecimal y2
) {
    public static AiDetectionResponse from(AiDetection detection) {
        return new AiDetectionResponse(
                detection.getId(),
                detection.getClassId(),
                detection.getClassName(),
                detection.getConfidence(),
                detection.getBboxX1(),
                detection.getBboxY1(),
                detection.getBboxX2(),
                detection.getBboxY2()
        );
    }
}
