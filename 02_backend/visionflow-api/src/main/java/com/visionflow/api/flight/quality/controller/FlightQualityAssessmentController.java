package com.visionflow.api.flight.quality.controller;

import com.visionflow.api.audit.domain.AuditAction;
import com.visionflow.api.audit.domain.AuditEntityType;
import com.visionflow.api.audit.service.AuditLogService;
import com.visionflow.api.flight.quality.domain.FlightQualityGrade;
import com.visionflow.api.flight.quality.dto.FlightQualityAssessmentResponse;
import com.visionflow.api.flight.quality.dto.FlightQualityBackfillResponse;
import com.visionflow.api.flight.quality.service.FlightQualityAssessmentService;
import com.visionflow.api.flight.quality.service.FlightQualityBackfillService;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/drones/{droneId}")
@Validated
public class FlightQualityAssessmentController {

    private final FlightQualityAssessmentService assessmentService;
    private final FlightQualityBackfillService backfillService;
    private final AuditLogService auditLogService;

    public FlightQualityAssessmentController(
            FlightQualityAssessmentService assessmentService,
            FlightQualityBackfillService backfillService,
            AuditLogService auditLogService
    ) {
        this.assessmentService = assessmentService;
        this.backfillService = backfillService;
        this.auditLogService = auditLogService;
    }

    @GetMapping(
            "/flight-sessions/{sessionId}/quality-assessment"
    )
    public FlightQualityAssessmentResponse findAssessment(
            @PathVariable
            @Positive(message = "드론 ID는 1 이상이어야 합니다.")
            Long droneId,

            @PathVariable
            @NotBlank(message = "비행 세션 ID는 필수입니다.")
            @Size(
                    max = 36,
                    message = "비행 세션 ID는 36자 이하여야 합니다."
            )
            String sessionId
    ) {
        return assessmentService.find(droneId, sessionId);
    }

    @PutMapping(
            "/flight-sessions/{sessionId}/quality-assessment"
    )
    public FlightQualityAssessmentResponse recalculateAssessment(
            @PathVariable
            @Positive(message = "드론 ID는 1 이상이어야 합니다.")
            Long droneId,

            @PathVariable
            @NotBlank(message = "비행 세션 ID는 필수입니다.")
            @Size(
                    max = 36,
                    message = "비행 세션 ID는 36자 이하여야 합니다."
            )
            String sessionId
    ) {
        FlightQualityAssessmentResponse response =
                assessmentService.recalculate(droneId, sessionId);
        auditLogService.record(
                AuditAction.FLIGHT_QUALITY_ASSESSED,
                AuditEntityType.FLIGHT_QUALITY_ASSESSMENT,
                sessionId,
                "비행 품질 평가 저장",
                Map.of(
                        "droneId", droneId,
                        "ruleVersion", response.ruleVersion(),
                        "score", response.score(),
                        "grade", response.grade().name()
                )
        );
        return response;
    }

    @GetMapping("/flight-quality-assessments")
    public List<FlightQualityAssessmentResponse> findHistory(
            @PathVariable
            @Positive(message = "드론 ID는 1 이상이어야 합니다.")
            Long droneId,

            @RequestParam(required = false)
            FlightQualityGrade grade,

            @RequestParam(defaultValue = "20")
            @Min(
                    value = 1,
                    message = "품질 평가 목록 제한값은 1 이상이어야 합니다."
            )
            @Max(
                    value = 100,
                    message = "품질 평가 목록 제한값은 100 이하여야 합니다."
            )
            Integer limit
    ) {
        return assessmentService.findHistory(
                droneId,
                grade,
                limit
        );
    }

    @PostMapping("/flight-quality-assessments/backfill")
    public FlightQualityBackfillResponse backfillAssessments(
            @PathVariable
            @Positive(message = "드론 ID는 1 이상이어야 합니다.")
            Long droneId,

            @RequestParam(defaultValue = "100")
            @Min(
                    value = 1,
                    message = "품질 평가 백필 제한값은 1 이상이어야 합니다."
            )
            @Max(
                    value = 100,
                    message = "품질 평가 백필 제한값은 100 이하여야 합니다."
            )
            Integer limit,

            @RequestParam(defaultValue = "false")
            boolean force
    ) {
        FlightQualityBackfillResponse response =
                backfillService.backfill(droneId, limit, force);
        auditLogService.record(
                AuditAction.FLIGHT_QUALITY_ASSESSED,
                AuditEntityType.FLIGHT_QUALITY_ASSESSMENT,
                droneId,
                "종료 비행 품질 평가 백필",
                Map.of(
                        "ruleVersion", response.ruleVersion(),
                        "force", response.force(),
                        "candidateCount", response.candidateCount(),
                        "evaluatedCount", response.evaluatedCount(),
                        "skippedCount", response.skippedCount(),
                        "failedCount", response.failedCount()
                )
        );
        return response;
    }
}
