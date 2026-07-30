package com.visionflow.api.drone.dto;

import com.visionflow.api.drone.domain.DroneTelemetrySource;
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Size;

import java.math.BigDecimal;
import java.time.LocalDateTime;

public record DroneTelemetryUpdateRequest(

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

        @DecimalMin(
                value = "0.0",
                message = "방위각은 0 이상이어야 합니다."
        )
        @DecimalMax(
                value = "360.0",
                message = "방위각은 360 이하여야 합니다."
        )
        BigDecimal heading,

        @DecimalMin(
                value = "-180.0",
                message = "피치는 -180 이상이어야 합니다."
        )
        @DecimalMax(
                value = "180.0",
                message = "피치는 180 이하여야 합니다."
        )
        BigDecimal pitch,

        @DecimalMin(
                value = "-90.0",
                message = "롤은 -90 이상이어야 합니다."
        )
        @DecimalMax(
                value = "90.0",
                message = "롤은 90 이하여야 합니다."
        )
        BigDecimal roll,

        @DecimalMin(
                value = "0.0",
                message = "지상 속도는 0 이상이어야 합니다."
        )
        BigDecimal groundSpeed,

        @DecimalMin(
                value = "0.0",
                message = "수평 정확도는 0 이상이어야 합니다."
        )
        BigDecimal horizontalAccuracy,

        @DecimalMin(
                value = "0.0",
                message = "수직 정확도는 0 이상이어야 합니다."
        )
        BigDecimal verticalAccuracy,

        DroneTelemetrySource telemetrySource,

        @Size(
                max = 100,
                message = "소스 기기 ID는 100자 이하여야 합니다."
        )
        String sourceDeviceId,

        @Size(
                max = 36,
                message = "비행 세션 ID는 36자 이하여야 합니다."
        )
        String flightSessionId,

        LocalDateTime lastConnectedAt
) {

    @AssertTrue(message = "갱신할 텔레메트리 값을 하나 이상 입력해야 합니다.")
    public boolean isTelemetryProvided() {
        return latitude != null
                || longitude != null
                || altitude != null
                || batteryLevel != null
                || heading != null
                || pitch != null
                || roll != null
                || groundSpeed != null
                || horizontalAccuracy != null
                || verticalAccuracy != null
                || lastConnectedAt != null;
    }

    @AssertTrue(message = "위도와 경도는 함께 입력해야 합니다.")
    public boolean isCoordinatePairValid() {
        return (latitude == null && longitude == null)
                || (latitude != null && longitude != null);
    }
}
