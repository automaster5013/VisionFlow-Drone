package com.visionflow.api.flight.quality.service;

import com.visionflow.api.ai.domain.AiInferenceEvent;
import com.visionflow.api.drone.domain.DroneTelemetryHistory;
import com.visionflow.api.flight.domain.FlightSessionStatus;
import com.visionflow.api.flight.quality.domain.FlightQualityGrade;
import com.visionflow.api.flight.quality.domain.FlightQualityRisk;
import com.visionflow.api.flight.quality.domain.FlightQualitySeverity;
import com.visionflow.api.flight.quality.domain.FlightQualitySnapshot;
import org.springframework.stereotype.Component;

import java.math.BigDecimal;
import java.time.Duration;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;

@Component
public class FlightQualityCalculator {

    private static final double MAX_REALISTIC_SPEED_METERS_PER_SECOND =
            60.0;
    private static final double ALTITUDE_SPIKE_METERS = 30.0;
    private static final long ALTITUDE_SPIKE_WINDOW_SECONDS = 5;

    public FlightQualitySnapshot calculate(
            FlightSessionStatus sessionStatus,
            List<DroneTelemetryHistory> telemetry,
            List<AiInferenceEvent> aiEvents
    ) {
        List<DroneTelemetryHistory> orderedTelemetry =
                telemetry.stream()
                        .sorted(
                                Comparator.comparing(
                                        DroneTelemetryHistory::getRecordedAt
                                )
                        )
                        .toList();
        List<AiInferenceEvent> orderedAiEvents =
                aiEvents.stream()
                        .sorted(
                                Comparator.comparing(
                                        AiInferenceEvent::getCapturedAt
                                )
                        )
                        .toList();

        int telemetryCount = orderedTelemetry.size();
        long validCoordinateCount =
                orderedTelemetry.stream()
                        .filter(this::hasValidCoordinate)
                        .count();
        List<Integer> batteryValues =
                orderedTelemetry.stream()
                        .map(DroneTelemetryHistory::getBatteryLevel)
                        .filter(value -> value != null)
                        .toList();
        double coordinateCoverage =
                ratio(validCoordinateCount, telemetryCount);
        double batteryCoverage =
                ratio(batteryValues.size(), telemetryCount);

        List<Double> gaps = new ArrayList<>();
        int unrealisticJumpCount = 0;
        int altitudeSpikeCount = 0;
        int batteryIncreaseCount = 0;

        for (int index = 1; index < orderedTelemetry.size(); index++) {
            DroneTelemetryHistory previous =
                    orderedTelemetry.get(index - 1);
            DroneTelemetryHistory current =
                    orderedTelemetry.get(index);
            double elapsedSeconds = elapsedSeconds(
                    previous.getRecordedAt(),
                    current.getRecordedAt()
            );

            if (elapsedSeconds <= 0) {
                continue;
            }

            gaps.add(elapsedSeconds);

            if (
                    hasValidCoordinate(previous)
                            && hasValidCoordinate(current)
                            && distanceMeters(previous, current)
                            / elapsedSeconds
                            > MAX_REALISTIC_SPEED_METERS_PER_SECOND
            ) {
                unrealisticJumpCount++;
            }

            if (
                    previous.getAltitude() != null
                            && current.getAltitude() != null
                            && elapsedSeconds
                            <= ALTITUDE_SPIKE_WINDOW_SECONDS
                            && current.getAltitude()
                            .subtract(previous.getAltitude())
                            .abs()
                            .doubleValue()
                            > ALTITUDE_SPIKE_METERS
            ) {
                altitudeSpikeCount++;
            }

            if (
                    previous.getBatteryLevel() != null
                            && current.getBatteryLevel() != null
                            && current.getBatteryLevel()
                            - previous.getBatteryLevel()
                            > 3
            ) {
                batteryIncreaseCount++;
            }
        }

        Double maximumGap =
                gaps.stream().max(Double::compareTo).orElse(null);
        List<Double> inferenceTimes =
                orderedAiEvents.stream()
                        .map(AiInferenceEvent::getInferenceMs)
                        .filter(value -> value != null)
                        .map(BigDecimal::doubleValue)
                        .toList();
        Double averageInferenceMs =
                inferenceTimes.isEmpty()
                        ? null
                        : inferenceTimes.stream()
                        .mapToDouble(Double::doubleValue)
                        .average()
                        .orElse(0);
        List<AiInferenceEvent> detectedEvents =
                orderedAiEvents.stream()
                        .filter(event ->
                                safeDetectionCount(event) > 0
                        )
                        .toList();
        long snapshotCount =
                detectedEvents.stream()
                        .filter(this::hasSnapshot)
                        .count();
        double snapshotCoverage =
                detectedEvents.isEmpty()
                        ? 1.0
                        : ratio(
                                snapshotCount,
                                detectedEvents.size()
                        );

        int baseDataScore =
                telemetryCount >= 2
                        ? 10
                        : telemetryCount == 1 ? 5 : 0;
        int cadenceScore =
                maximumGap == null
                        ? 0
                        : maximumGap <= 3
                        ? 15
                        : maximumGap <= 10
                        ? 10
                        : maximumGap <= 30 ? 5 : 0;
        int dataScore = (int) Math.round(
                baseDataScore
                        + coordinateCoverage * 15
                        + cadenceScore
        );
        int flightScore = (int) Math.round(
                Math.max(0, 12 - unrealisticJumpCount * 4)
                        + Math.max(0, 8 - altitudeSpikeCount * 2)
                        + batteryCoverage * 5
                        + (
                        batteryValues.isEmpty()
                                ? 0
                                : Math.max(
                                        0,
                                        5 - batteryIncreaseCount * 2
                                )
                )
        );
        int inferenceScore =
                averageInferenceMs == null
                        ? 0
                        : averageInferenceMs <= 200
                        ? 10
                        : averageInferenceMs <= 500
                        ? 7
                        : averageInferenceMs <= 1_000 ? 3 : 0;
        int aiScore = (int) Math.round(
                (orderedAiEvents.isEmpty() ? 0 : 15)
                        + inferenceScore
                        + (
                        orderedAiEvents.isEmpty()
                                ? 0
                                : snapshotCoverage * 5
                )
        );

        Integer minimumBattery =
                batteryValues.stream()
                        .min(Integer::compareTo)
                        .orElse(null);
        List<FlightQualityRisk> risks = collectRisks(
                sessionStatus,
                telemetryCount,
                coordinateCoverage,
                maximumGap,
                unrealisticJumpCount,
                altitudeSpikeCount,
                batteryCoverage,
                minimumBattery,
                orderedAiEvents.size(),
                averageInferenceMs,
                detectedEvents.size(),
                snapshotCoverage
        );
        int criticalCount = (int) risks.stream()
                .filter(risk ->
                        risk.severity()
                                == FlightQualitySeverity.CRITICAL
                )
                .count();
        int warningCount = risks.size() - criticalCount;
        int rawScore = clampScore(dataScore + flightScore + aiScore);
        int score =
                criticalCount > 0
                        ? Math.min(rawScore, 74)
                        : rawScore;
        FlightQualityGrade grade = grade(score);

        return new FlightQualitySnapshot(
                sessionStatus,
                score,
                grade,
                dataScore,
                flightScore,
                aiScore,
                telemetryCount,
                validCoordinateCount,
                coordinateCoverage * 100,
                batteryCoverage * 100,
                maximumGap,
                unrealisticJumpCount,
                altitudeSpikeCount,
                batteryIncreaseCount,
                minimumBattery,
                orderedAiEvents.size(),
                detectedEvents.size(),
                averageInferenceMs,
                snapshotCoverage * 100,
                warningCount,
                criticalCount,
                risks.isEmpty() ? null : risks.get(0)
        );
    }

    private List<FlightQualityRisk> collectRisks(
            FlightSessionStatus sessionStatus,
            int telemetryCount,
            double coordinateCoverage,
            Double maximumGap,
            int unrealisticJumpCount,
            int altitudeSpikeCount,
            double batteryCoverage,
            Integer minimumBattery,
            int aiEventCount,
            Double averageInferenceMs,
            int detectedEventCount,
            double snapshotCoverage
    ) {
        List<FlightQualityRisk> risks = new ArrayList<>();

        if (sessionStatus == FlightSessionStatus.ABORTED) {
            risks.add(critical(
                    "중단된 비행 세션",
                    "중단 원인과 당시 이벤트를 확인해야 합니다."
            ));
        }
        if (telemetryCount < 2) {
            risks.add(critical(
                    "텔레메트리 표본 부족",
                    "저장된 텔레메트리가 "
                            + telemetryCount
                            + "개입니다."
            ));
        } else if (coordinateCoverage < 0.8) {
            risks.add(warning(
                    "GPS 좌표 보존율 저하",
                    String.format(
                            Locale.ROOT,
                            "유효 좌표 비율 %.1f%%",
                            coordinateCoverage * 100
                    )
            ));
        }
        if (
                telemetryCount >= 2
                        && (
                        maximumGap == null
                                || maximumGap > 10
                )
        ) {
            risks.add(warning(
                    "텔레메트리 수신 공백",
                    maximumGap == null
                            ? "기록 간격을 계산할 수 없습니다."
                            : String.format(
                                    Locale.ROOT,
                                    "최대 공백 %.1f초",
                                    maximumGap
                            )
            ));
        }
        if (unrealisticJumpCount > 0) {
            risks.add(warning(
                    "GPS 위치 점프",
                    "비현실적인 좌표 변화 "
                            + unrealisticJumpCount
                            + "회"
            ));
        }
        if (altitudeSpikeCount > 0) {
            risks.add(warning(
                    "고도 급변",
                    "급격한 고도 변화 "
                            + altitudeSpikeCount
                            + "회"
            ));
        }
        if (telemetryCount > 0 && batteryCoverage < 0.8) {
            risks.add(warning(
                    "배터리 값 보존율 저하",
                    String.format(
                            Locale.ROOT,
                            "배터리 값 보존율 %.1f%%",
                            batteryCoverage * 100
                    )
            ));
        }
        if (minimumBattery != null && minimumBattery < 15) {
            risks.add(critical(
                    "위험 배터리",
                    "최저 배터리 " + minimumBattery + "%"
            ));
        } else if (minimumBattery != null && minimumBattery < 25) {
            risks.add(warning(
                    "저전력 비행",
                    "최저 배터리 " + minimumBattery + "%"
            ));
        }
        if (aiEventCount == 0) {
            risks.add(warning(
                    "AI 추론 기록 없음",
                    "비행 세션과 연결된 AI 이벤트가 없습니다."
            ));
        } else if (
                averageInferenceMs != null
                        && averageInferenceMs > 1_000
        ) {
            risks.add(critical(
                    "AI 추론 지연 위험",
                    String.format(
                            Locale.ROOT,
                            "평균 %.1fms",
                            averageInferenceMs
                    )
            ));
        } else if (
                averageInferenceMs != null
                        && averageInferenceMs > 500
        ) {
            risks.add(warning(
                    "AI 추론 지연 주의",
                    String.format(
                            Locale.ROOT,
                            "평균 %.1fms",
                            averageInferenceMs
                    )
            ));
        }
        if (detectedEventCount > 0 && snapshotCoverage < 1) {
            risks.add(warning(
                    "탐지 증적 이미지 누락",
                    String.format(
                            Locale.ROOT,
                            "스냅샷 보존율 %.1f%%",
                            snapshotCoverage * 100
                    )
            ));
        }

        risks.sort(
                Comparator.comparingInt(risk ->
                        risk.severity()
                                == FlightQualitySeverity.CRITICAL
                                ? 0
                                : 1
                )
        );
        return risks;
    }

    private FlightQualityRisk critical(
            String title,
            String detail
    ) {
        return new FlightQualityRisk(
                FlightQualitySeverity.CRITICAL,
                title,
                detail
        );
    }

    private FlightQualityRisk warning(
            String title,
            String detail
    ) {
        return new FlightQualityRisk(
                FlightQualitySeverity.WARNING,
                title,
                detail
        );
    }

    private boolean hasValidCoordinate(
            DroneTelemetryHistory telemetry
    ) {
        if (
                telemetry.getLatitude() == null
                        || telemetry.getLongitude() == null
        ) {
            return false;
        }

        double latitude = telemetry.getLatitude().doubleValue();
        double longitude = telemetry.getLongitude().doubleValue();
        return latitude >= -90
                && latitude <= 90
                && longitude >= -180
                && longitude <= 180;
    }

    private double distanceMeters(
            DroneTelemetryHistory first,
            DroneTelemetryHistory second
    ) {
        double earthRadiusMeters = 6_371_000;
        double latitudeDelta = Math.toRadians(
                second.getLatitude().doubleValue()
                        - first.getLatitude().doubleValue()
        );
        double longitudeDelta = Math.toRadians(
                second.getLongitude().doubleValue()
                        - first.getLongitude().doubleValue()
        );
        double firstLatitude = Math.toRadians(
                first.getLatitude().doubleValue()
        );
        double secondLatitude = Math.toRadians(
                second.getLatitude().doubleValue()
        );
        double haversine =
                Math.pow(Math.sin(latitudeDelta / 2), 2)
                        + Math.cos(firstLatitude)
                        * Math.cos(secondLatitude)
                        * Math.pow(
                                Math.sin(longitudeDelta / 2),
                                2
                        );

        return 2
                * earthRadiusMeters
                * Math.atan2(
                        Math.sqrt(haversine),
                        Math.sqrt(1 - haversine)
                );
    }

    private double elapsedSeconds(
            LocalDateTime first,
            LocalDateTime second
    ) {
        return Duration.between(first, second).toNanos()
                / 1_000_000_000.0;
    }

    private boolean hasSnapshot(AiInferenceEvent event) {
        return event.getSnapshotFileName() != null
                && !event.getSnapshotFileName().isBlank();
    }

    private int safeDetectionCount(AiInferenceEvent event) {
        return event.getDetectionCount() == null
                ? 0
                : event.getDetectionCount();
    }

    private double ratio(long numerator, long denominator) {
        return denominator == 0
                ? 0
                : (double) numerator / denominator;
    }

    private int clampScore(int value) {
        return Math.max(0, Math.min(100, value));
    }

    private FlightQualityGrade grade(int score) {
        if (score >= 90) {
            return FlightQualityGrade.EXCELLENT;
        }
        if (score >= 75) {
            return FlightQualityGrade.GOOD;
        }
        if (score >= 60) {
            return FlightQualityGrade.CAUTION;
        }
        return FlightQualityGrade.RISK;
    }
}
