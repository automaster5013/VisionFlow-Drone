package com.visionflow.api.flight.controller;

import com.visionflow.api.audit.domain.AuditAction;
import com.visionflow.api.audit.domain.AuditEntityType;
import com.visionflow.api.audit.service.AuditLogService;
import com.visionflow.api.flight.dto.FlightSessionReplayResponse;
import com.visionflow.api.flight.dto.FlightSessionResponse;
import com.visionflow.api.flight.dto.FlightSessionStartRequest;
import com.visionflow.api.flight.dto.FlightSessionSummaryResponse;
import com.visionflow.api.flight.dto.FlightSessionUpdateRequest;
import com.visionflow.api.flight.service.FlightSessionManagementService;
import com.visionflow.api.flight.service.FlightSessionReplayService;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping(
        "/api/drones/{droneId}/flight-sessions"
)
@Validated
public class FlightSessionReplayController {

    private final FlightSessionReplayService replayService;
    private final FlightSessionManagementService managementService;
    private final AuditLogService auditLogService;

    public FlightSessionReplayController(
            FlightSessionReplayService replayService,
            FlightSessionManagementService managementService,
            AuditLogService auditLogService
    ) {
        this.replayService = replayService;
        this.managementService = managementService;
        this.auditLogService = auditLogService;
    }

    @PostMapping
    public ResponseEntity<FlightSessionResponse> startSession(
            @PathVariable
            @Positive(message = "드론 ID는 1 이상이어야 합니다.")
            Long droneId,

            @Valid
            @RequestBody
            FlightSessionStartRequest request
    ) {
        FlightSessionResponse response = managementService.start(
                droneId,
                request
        );
        auditLogService.record(
                AuditAction.FLIGHT_SESSION_STARTED,
                AuditEntityType.FLIGHT_SESSION,
                response.sessionId(),
                "비행 세션 시작",
                Map.of(
                        "droneId", droneId,
                        "status", response.status().name(),
                        "name", response.name()
                )
        );
        return ResponseEntity
                .status(HttpStatus.CREATED)
                .body(response);
    }

    @GetMapping
    public List<FlightSessionSummaryResponse> findSessions(
            @PathVariable
            @Positive(message = "드론 ID는 1 이상이어야 합니다.")
            Long droneId,

            @RequestParam(required = false)
            @Size(
                    max = 36,
                    message = "비행 세션 검색어는 36자 이하여야 합니다."
            )
            String query,

            @RequestParam(defaultValue = "20")
            @Min(
                    value = 1,
                    message = "세션 목록 제한값은 1 이상이어야 합니다."
            )
            @Max(
                    value = 100,
                    message = "세션 목록 제한값은 100 이하여야 합니다."
            )
            Integer limit
    ) {
        return replayService.findSessions(
                droneId,
                query,
                limit
        );
    }

    @GetMapping("/{sessionId}")
    public FlightSessionResponse findSession(
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
        return managementService.find(droneId, sessionId);
    }

    @PatchMapping("/{sessionId}")
    public FlightSessionResponse updateSession(
            @PathVariable
            @Positive(message = "드론 ID는 1 이상이어야 합니다.")
            Long droneId,

            @PathVariable
            @NotBlank(message = "비행 세션 ID는 필수입니다.")
            @Size(
                    max = 36,
                    message = "비행 세션 ID는 36자 이하여야 합니다."
            )
            String sessionId,

            @Valid
            @RequestBody
            FlightSessionUpdateRequest request
    ) {
        FlightSessionResponse response = managementService.update(
                droneId,
                sessionId,
                request
        );
        auditLogService.record(
                AuditAction.FLIGHT_SESSION_UPDATED,
                AuditEntityType.FLIGHT_SESSION,
                response.sessionId(),
                "비행 세션 정보 수정",
                Map.of(
                        "droneId", droneId,
                        "status", response.status().name(),
                        "name", response.name()
                )
        );
        return response;
    }

    @PostMapping("/{sessionId}/complete")
    public FlightSessionResponse completeSession(
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
        FlightSessionResponse response = managementService.complete(
                droneId,
                sessionId
        );
        auditLogService.record(
                AuditAction.FLIGHT_SESSION_COMPLETED,
                AuditEntityType.FLIGHT_SESSION,
                response.sessionId(),
                "비행 세션 완료",
                Map.of(
                        "droneId", droneId,
                        "status", response.status().name()
                )
        );
        return response;
    }

    @PostMapping("/{sessionId}/abort")
    public FlightSessionResponse abortSession(
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
        FlightSessionResponse response = managementService.abort(
                droneId,
                sessionId
        );
        auditLogService.record(
                AuditAction.FLIGHT_SESSION_ABORTED,
                AuditEntityType.FLIGHT_SESSION,
                response.sessionId(),
                "비행 세션 중단",
                Map.of(
                        "droneId", droneId,
                        "status", response.status().name()
                )
        );
        return response;
    }

    @GetMapping("/{sessionId}/replay")
    public FlightSessionReplayResponse findReplay(
            @PathVariable
            @Positive(message = "드론 ID는 1 이상이어야 합니다.")
            Long droneId,

            @PathVariable
            @NotBlank(message = "비행 세션 ID는 필수입니다.")
            @Size(
                    max = 36,
                    message = "비행 세션 ID는 36자 이하여야 합니다."
            )
            String sessionId,

            @RequestParam(defaultValue = "5000")
            @Min(
                    value = 1,
                    message = "텔레메트리 제한값은 1 이상이어야 합니다."
            )
            @Max(
                    value = 5000,
                    message = "텔레메트리 제한값은 5000 이하여야 합니다."
            )
            Integer telemetryLimit,

            @RequestParam(defaultValue = "200")
            @Min(
                    value = 1,
                    message = "AI 이벤트 제한값은 1 이상이어야 합니다."
            )
            @Max(
                    value = 1000,
                    message = "AI 이벤트 제한값은 1000 이하여야 합니다."
            )
            Integer eventLimit
    ) {
        return replayService.findReplay(
                droneId,
                sessionId,
                telemetryLimit,
                eventLimit
        );
    }
}
