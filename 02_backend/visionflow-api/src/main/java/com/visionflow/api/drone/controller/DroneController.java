package com.visionflow.api.drone.controller;

import com.visionflow.api.common.response.ApiResponse;
import com.visionflow.api.common.response.DeleteResponse;
import com.visionflow.api.drone.domain.DroneStatus;
import com.visionflow.api.drone.dto.DroneCreateRequest;
import com.visionflow.api.drone.dto.DroneResponse;
import com.visionflow.api.drone.dto.DroneStatusUpdateRequest;
import com.visionflow.api.drone.dto.DroneUpdateRequest;
import com.visionflow.api.drone.service.DroneService;
import com.visionflow.api.drone.dto.DroneTelemetryUpdateRequest;
import com.visionflow.api.drone.dto.DroneTelemetryHistoryResponse;
import com.visionflow.api.drone.service.DroneTelemetryHistoryService;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Positive;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.web.bind.annotation.RequestParam;

import java.time.LocalDateTime;
import java.util.List;

@RestController
@RequestMapping("/api/drones")
@Validated
public class DroneController {

    private final DroneService droneService;
    private final DroneTelemetryHistoryService telemetryHistoryService;

    public DroneController(
            DroneService droneService,
            DroneTelemetryHistoryService telemetryHistoryService
    ) {
        this.droneService = droneService;
        this.telemetryHistoryService =
                telemetryHistoryService;
    }

    @PostMapping
    public ResponseEntity<ApiResponse<DroneResponse>> createDrone(
            @Valid @RequestBody DroneCreateRequest request
    ) {
        DroneResponse response = droneService.createDrone(request);

        return ResponseEntity
                .status(HttpStatus.CREATED)
                .body(ApiResponse.success(response));
    }

    @GetMapping
    public ResponseEntity<ApiResponse<List<DroneResponse>>> getDrones(
            @RequestParam(required = false) DroneStatus status
    ) {
        List<DroneResponse> response = droneService.getDrones(status);

        return ResponseEntity.ok(
                ApiResponse.success(response)
        );
    }

    @GetMapping("/{id}")
    public ResponseEntity<ApiResponse<DroneResponse>> getDrone(
            @PathVariable
            @Positive(message = "드론 ID는 1 이상의 값이어야 합니다.")
            Long id
    ) {
        DroneResponse response = droneService.getDrone(id);

        return ResponseEntity.ok(
                ApiResponse.success(response)
        );
    }

    @PutMapping("/{id}")
    public ResponseEntity<ApiResponse<DroneResponse>> updateDrone(
            @PathVariable
            @Positive(message = "드론 ID는 1 이상의 값이어야 합니다.")
            Long id,

            @Valid
            @RequestBody
            DroneUpdateRequest request
    ) {
        DroneResponse response = droneService.updateDrone(id, request);

        return ResponseEntity.ok(
                ApiResponse.success(response)
        );
    }

    @PatchMapping("/{id}/status")
    public ResponseEntity<ApiResponse<DroneResponse>> updateDroneStatus(
            @PathVariable
            @Positive(message = "드론 ID는 1 이상의 값이어야 합니다.")
            Long id,

            @Valid
            @RequestBody
            DroneStatusUpdateRequest request
    ) {
        DroneResponse response = droneService.updateStatus(id, request);

        return ResponseEntity.ok(
                ApiResponse.success(response)
        );
    }

    @PatchMapping("/{id}/telemetry")
    public ResponseEntity<ApiResponse<DroneResponse>> updateDroneTelemetry(
            @PathVariable
            @Positive(message = "드론 ID는 1 이상의 값이어야 합니다.")
            Long id,

            @Valid
            @RequestBody
            DroneTelemetryUpdateRequest request
    ) {
        DroneResponse response =
                droneService.updateTelemetry(id, request);

        return ResponseEntity.ok(
                ApiResponse.success(response)
        );
    }

    @DeleteMapping("/{id}")
    public ResponseEntity<ApiResponse<DeleteResponse>> deleteDrone(
            @PathVariable
            @Positive(message = "드론 ID는 1 이상의 값이어야 합니다.")
            Long id
    ) {
        droneService.deleteDrone(id);

        DeleteResponse response = new DeleteResponse(
                id,
                "드론이 삭제되었습니다."
        );

        return ResponseEntity.ok(
                ApiResponse.success(response)
        );
    }

    @GetMapping("/{id}/telemetry/history")
    public List<DroneTelemetryHistoryResponse> getTelemetryHistory(
            @PathVariable Long id,

            @RequestParam(required = false)
            @DateTimeFormat(
                    iso = DateTimeFormat.ISO.DATE_TIME
            )
            LocalDateTime from,

            @RequestParam(required = false)
            @DateTimeFormat(
                    iso = DateTimeFormat.ISO.DATE_TIME
            )
            LocalDateTime to,

            @RequestParam(
                    required = false,
                    defaultValue = "500"
            )
            Integer limit
    ) {
        // 기존 서비스의 드론 존재 여부 검증 재사용
        droneService.getDrone(id);

        return telemetryHistoryService.getHistory(
                id,
                from,
                to,
                limit
        );
    }
}