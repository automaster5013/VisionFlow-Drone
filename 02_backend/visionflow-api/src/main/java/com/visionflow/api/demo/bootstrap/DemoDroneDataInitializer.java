package com.visionflow.api.demo.bootstrap;

import com.visionflow.api.drone.domain.DroneStatus;
import com.visionflow.api.drone.dto.DroneCreateRequest;
import com.visionflow.api.drone.repository.DroneRepository;
import com.visionflow.api.drone.service.DroneService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

import java.math.BigDecimal;

@Component
@ConditionalOnProperty(
        name = "visionflow.demo.seed-drones",
        havingValue = "true"
)
public class DemoDroneDataInitializer implements ApplicationRunner {

    private static final Logger log =
            LoggerFactory.getLogger(DemoDroneDataInitializer.class);

    private final DroneRepository droneRepository;
    private final DroneService droneService;

    public DemoDroneDataInitializer(
            DroneRepository droneRepository,
            DroneService droneService
    ) {
        this.droneRepository = droneRepository;
        this.droneService = droneService;
    }

    @Override
    public void run(ApplicationArguments args) {
        createIfMissing(
                "DRONE-001",
                "Vision Eagle 1",
                "VF-DT-001",
                "37.5665000",
                "126.9780000",
                "48.20",
                84
        );
        createIfMissing(
                "DRONE-002",
                "Vision Eagle 2",
                "VF-DT-002",
                "37.5652000",
                "126.9825000",
                "45.30",
                87
        );
        createIfMissing(
                "DRONE-003",
                "Vision Eagle 3",
                "VF-DT-003",
                "37.5680000",
                "126.9750000",
                "0.00",
                100
        );
    }

    private void createIfMissing(
            String droneCode,
            String name,
            String serialNumber,
            String latitude,
            String longitude,
            String altitude,
            int batteryLevel
    ) {
        if (droneRepository.existsByDroneCode(droneCode)) {
            return;
        }

        if (droneRepository.existsBySerialNumber(serialNumber)) {
            log.warn(
                    "동일한 시리얼 번호가 이미 등록되어 시연용 드론 생성을 건너뜁니다: {}",
                    serialNumber
            );
            return;
        }

        droneService.createDrone(new DroneCreateRequest(
                droneCode,
                name,
                "Custom Vision Drone",
                serialNumber,
                DroneStatus.OFFLINE,
                null,
                new BigDecimal(latitude),
                new BigDecimal(longitude),
                new BigDecimal(altitude),
                batteryLevel,
                null
        ));
        log.info("시연용 드론을 자동 등록했습니다: {}", droneCode);
    }
}
