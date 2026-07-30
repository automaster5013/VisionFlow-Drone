package com.visionflow.api.ai.service;

import com.visionflow.api.ai.domain.AiAlertSeverity;
import com.visionflow.api.ai.domain.AiDetection;
import org.springframework.stereotype.Component;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Set;

@Component
public class AiAlertRiskEvaluator {

    private static final Set<String> CRITICAL_CLASSES = Set.of(
            "fire",
            "smoke",
            "gun",
            "knife",
            "weapon",
            "accident",
            "fight"
    );

    private static final BigDecimal CRITICAL_CONFIDENCE =
            new BigDecimal("0.60");

    private static final BigDecimal WARNING_CONFIDENCE =
            new BigDecimal("0.70");

    public RiskAssessment evaluate(List<AiDetection> detections) {
        if (detections == null || detections.isEmpty()) {
            throw new IllegalArgumentException(
                    "AI 경보 위험도를 계산하려면 탐지 결과가 필요합니다."
            );
        }

        AiDetection primary = detections.stream()
                .max(Comparator.comparing(AiDetection::getConfidence))
                .orElseThrow();

        boolean critical = detections.stream()
                .anyMatch(this::isCriticalDetection);

        AiAlertSeverity severity;
        if (critical) {
            severity = AiAlertSeverity.CRITICAL;
        } else if (
                primary.getConfidence().compareTo(WARNING_CONFIDENCE) >= 0
                        || detections.size() >= 3
        ) {
            severity = AiAlertSeverity.WARNING;
        } else {
            severity = AiAlertSeverity.INFO;
        }

        String severityLabel = switch (severity) {
            case INFO -> "AI 객체 탐지";
            case WARNING -> "주의 탐지";
            case CRITICAL -> "긴급 탐지";
        };

        BigDecimal confidencePercent = primary.getConfidence()
                .multiply(BigDecimal.valueOf(100))
                .setScale(1, RoundingMode.HALF_UP);

        return new RiskAssessment(
                severity,
                severityLabel + ": " + primary.getClassName(),
                detections.size()
                        + "개 객체 탐지 · 최고 신뢰도 "
                        + confidencePercent.toPlainString()
                        + "%",
                primary.getClassName(),
                primary.getConfidence()
        );
    }

    private boolean isCriticalDetection(AiDetection detection) {
        String normalizedClassName = detection.getClassName()
                .trim()
                .toLowerCase(Locale.ROOT);

        return CRITICAL_CLASSES.contains(normalizedClassName)
                && detection.getConfidence()
                .compareTo(CRITICAL_CONFIDENCE) >= 0;
    }

    public record RiskAssessment(
            AiAlertSeverity severity,
            String title,
            String summary,
            String primaryClassName,
            BigDecimal maxConfidence
    ) {
    }
}
