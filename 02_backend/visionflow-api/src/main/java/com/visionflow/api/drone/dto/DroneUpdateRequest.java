package com.visionflow.api.drone.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record DroneUpdateRequest(

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

        @Size(
                max = 500,
                message = "RTSP URL은 500자 이하로 입력해야 합니다."
        )
        String rtspUrl
) {
}