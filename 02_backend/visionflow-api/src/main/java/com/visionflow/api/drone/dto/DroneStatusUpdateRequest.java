package com.visionflow.api.drone.dto;

import com.visionflow.api.drone.domain.DroneStatus;
import jakarta.validation.constraints.NotNull;

public record DroneStatusUpdateRequest(

        @NotNull(message = "변경할 드론 상태는 필수입니다.")
        DroneStatus status
) {
}