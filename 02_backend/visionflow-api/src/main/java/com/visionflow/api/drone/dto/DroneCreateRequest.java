package com.visionflow.api.drone.dto;

import com.visionflow.api.drone.domain.DroneStatus;
import jakarta.validation.constraints.*;

import java.math.BigDecimal;
import java.time.LocalDateTime;

public record DroneCreateRequest(

        @NotBlank(message = "드론 코드는 필수입니다.")
        @Size(
                max = 50,
                message = "드론 코드는 50자 이하로 입력해야 합니다."
        )
        @Pattern(
                regexp = "^[A-Za-z0-9_-]+$",
                message = "드론 코드는 영문, 숫자, 하이픈, 밑줄만 사용할 수 있습니다."
        )
        String droneCode,

        @NotBlank(message = "드론 이름은 필수입니다.")
        @Size(
                max = 100,
                message = "드론 이름은 100자 이하로 입력해야 합니다."
        )
        String name,

        @Size(
                max = 100,
                message = "모델명은 100자 이하로 입력해야 합니다."
        )
        String modelName,

        @Size(
                max = 100,
                message = "시리얼 번호는 100자 이하로 입력해야 합니다."
        )
        String serialNumber,

        DroneStatus status,

        @Size(
                max = 500,
                message = "RTSP URL은 500자 이하로 입력해야 합니다."
        )
        String rtspUrl,

        @DecimalMin(
                value = "-90.0",
                message = "위도는 -90 이상이어야 합니다."
        )
        @DecimalMax(
                value = "90.0",
                message = "위도는 90 이하여야 합니다."
        )
        BigDecimal latitude,

        @DecimalMin(
                value = "-180.0",
                message = "경도는 -180 이상이어야 합니다."
        )
        @DecimalMax(
                value = "180.0",
                message = "경도는 180 이하여야 합니다."
        )
        BigDecimal longitude,

        BigDecimal altitude,

        @Min(
                value = 0,
                message = "배터리 잔량은 0 이상이어야 합니다."
        )
        @Max(
                value = 100,
                message = "배터리 잔량은 100 이하여야 합니다."
        )
        Integer batteryLevel,

        LocalDateTime lastConnectedAt
) {
}