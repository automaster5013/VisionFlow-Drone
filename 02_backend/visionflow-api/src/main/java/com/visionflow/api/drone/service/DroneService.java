package com.visionflow.api.drone.service;

import com.visionflow.api.drone.realtime.DroneRealtimePublisher;
import com.visionflow.api.common.exception.DuplicateResourceException;
import com.visionflow.api.common.exception.ResourceNotFoundException;
import com.visionflow.api.drone.domain.Drone;
import com.visionflow.api.drone.domain.DroneStatus;
import com.visionflow.api.drone.domain.DroneTelemetrySource;
import com.visionflow.api.drone.dto.DroneCreateRequest;
import com.visionflow.api.drone.dto.DroneResponse;
import com.visionflow.api.drone.dto.DroneStatusUpdateRequest;
import com.visionflow.api.drone.dto.DroneUpdateRequest;
import com.visionflow.api.drone.exception.DroneHistoryDeleteDeniedException;
import com.visionflow.api.drone.repository.DroneRepository;
import com.visionflow.api.drone.dto.DroneTelemetryUpdateRequest;
import com.visionflow.api.geofence.service.GeofenceService;
import com.visionflow.api.flight.service.FlightSessionCorrelationGuard;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.List;

@Service
@Transactional(readOnly = true)
public class DroneService {

    private final DroneRepository droneRepository;
    private final DroneRealtimePublisher realtimePublisher;
    private final DroneTelemetryHistoryService telemetryHistoryService;
    private final GeofenceService geofenceService;
    private final FlightSessionCorrelationGuard sessionCorrelationGuard;

    public DroneService(
            DroneRepository droneRepository,
            DroneRealtimePublisher realtimePublisher,
            DroneTelemetryHistoryService telemetryHistoryService,
            GeofenceService geofenceService,
            FlightSessionCorrelationGuard sessionCorrelationGuard
    ) {
        this.droneRepository = droneRepository;
        this.realtimePublisher = realtimePublisher;
        this.telemetryHistoryService = telemetryHistoryService;
        this.geofenceService = geofenceService;
        this.sessionCorrelationGuard = sessionCorrelationGuard;
    }

    @Transactional
    public DroneResponse createDrone(
            DroneCreateRequest request
    ) {
        String droneCode = normalizeRequired(request.droneCode());
        String serialNumber = normalizeNullable(request.serialNumber());

        validateDuplicateDroneCode(droneCode);
        validateDuplicateSerialNumber(serialNumber);

        Drone drone = new Drone(
                droneCode,
                normalizeRequired(request.name()),
                normalizeNullable(request.modelName()),
                serialNumber,
                request.status(),
                normalizeNullable(request.rtspUrl()),
                request.latitude(),
                request.longitude(),
                request.altitude(),
                request.batteryLevel(),
                request.lastConnectedAt()
        );

        Drone savedDrone = droneRepository.save(drone);

        return DroneResponse.from(savedDrone);
    }

    public List<DroneResponse> getDrones(
            DroneStatus status
    ) {
        List<Drone> drones;

        if (status == null) {
            drones = droneRepository.findAllByOrderByCreatedAtDesc();
        } else {
            drones = droneRepository
                    .findAllByStatusOrderByCreatedAtDesc(status);
        }

        return drones.stream()
                .map(DroneResponse::from)
                .toList();
    }

    public DroneResponse getDrone(
            Long id
    ) {
        Drone drone = findDroneById(id);

        return DroneResponse.from(drone);
    }

    @Transactional
    public DroneResponse updateDrone(
            Long id,
            DroneUpdateRequest request
    ) {
        Drone drone = findDroneById(id);

        String serialNumber = normalizeNullable(request.serialNumber());

        validateDuplicateSerialNumberForUpdate(
                serialNumber,
                id
        );

        drone.updateBasicInformation(
                normalizeRequired(request.name()),
                normalizeNullable(request.modelName()),
                serialNumber,
                normalizeNullable(request.rtspUrl())
        );

        return DroneResponse.from(drone);
    }

    @Transactional
    public DroneResponse updateStatus(
            Long id,
            DroneStatusUpdateRequest request
    ) {
        Drone drone = findDroneById(id);

        drone.updateStatus(request.status());

        return DroneResponse.from(drone);
    }

    @Transactional(isolation = Isolation.SERIALIZABLE)
    public void deleteDrone(
            Long id
    ) {
        Drone drone = droneRepository.findByIdForUpdate(id)
                .orElseThrow(() -> new ResourceNotFoundException(
                        "ID가 " + id + "인 드론을 찾을 수 없습니다."
                ));

        if (droneRepository.countDeletionDependencies(id) > 0) {
            throw new DroneHistoryDeleteDeniedException(
                    "운영 이력이 있는 드론은 삭제할 수 없습니다. "
                            + "상태를 OFFLINE으로 변경해 이력을 보존해 주세요."
            );
        }

        droneRepository.delete(drone);
    }

    private Drone findDroneById(
            Long id
    ) {
        return droneRepository
                .findById(id)
                .orElseThrow(() ->
                        new ResourceNotFoundException(
                                "ID가 " + id + "인 드론을 찾을 수 없습니다."
                        )
                );
    }

    private void validateDuplicateDroneCode(
            String droneCode
    ) {
        if (droneRepository.existsByDroneCode(droneCode)) {
            throw new DuplicateResourceException(
                    "이미 등록된 드론 코드입니다: " + droneCode
            );
        }
    }

    private void validateDuplicateSerialNumber(
            String serialNumber
    ) {
        if (serialNumber == null) {
            return;
        }

        if (droneRepository.existsBySerialNumber(serialNumber)) {
            throw new DuplicateResourceException(
                    "이미 등록된 시리얼 번호입니다: " + serialNumber
            );
        }
    }

    private void validateDuplicateSerialNumberForUpdate(
            String serialNumber,
            Long droneId
    ) {
        if (serialNumber == null) {
            return;
        }

        boolean duplicated =
                droneRepository.existsBySerialNumberAndIdNot(
                        serialNumber,
                        droneId
                );

        if (duplicated) {
            throw new DuplicateResourceException(
                    "이미 등록된 시리얼 번호입니다: " + serialNumber
            );
        }
    }

    private String normalizeRequired(
            String value
    ) {
        return value.trim();
    }

    private String normalizeNullable(
            String value
    ) {
        if (value == null) {
            return null;
        }

        String trimmed = value.trim();

        return trimmed.isEmpty()
                ? null
                : trimmed;
    }

    @Transactional
    public DroneResponse updateTelemetry(
            Long id,
            DroneTelemetryUpdateRequest request
    ) {
        Drone drone = droneRepository.findById(id)
                .orElseThrow(() ->
                        new ResourceNotFoundException(
                                "드론을 찾을 수 없습니다. id=" + id
                        )
                );

        String flightSessionId =
                sessionCorrelationGuard.requireOptionalOwnedSession(
                        request.flightSessionId(),
                        id
                );

        LocalDateTime connectedAt =
                request.lastConnectedAt() != null
                        ? request.lastConnectedAt()
                        : LocalDateTime.now();

        drone.updateTelemetry(
                request.latitude(),
                request.longitude(),
                request.altitude(),
                request.batteryLevel(),
                request.heading(),
                request.pitch(),
                request.roll(),
                request.groundSpeed(),
                request.horizontalAccuracy(),
                request.verticalAccuracy(),
                request.telemetrySource() != null
                        ? request.telemetrySource()
                        : DroneTelemetrySource.API,
                normalizeNullable(request.sourceDeviceId()),
                flightSessionId,
                connectedAt
        );

        droneRepository.flush();

        // 같은 트랜잭션에서 이력 저장
        telemetryHistoryService.record(drone, connectedAt);
        geofenceService.evaluate(drone, connectedAt);

        DroneResponse response = DroneResponse.from(drone);
        realtimePublisher.publish(response);

        return response;
    }
}
