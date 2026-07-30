package com.visionflow.api.maintenance.dto;

import com.visionflow.api.maintenance.domain.MaintenanceCompletionDecision;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record MaintenanceInspectionCompleteRequest(
        @NotNull(message = "점검 판정은 필수입니다.")
        MaintenanceCompletionDecision decision,

        @NotBlank(message = "점검 결과는 필수입니다.")
        @Size(max = 1000, message = "점검 결과는 1000자 이하여야 합니다.")
        String finding,

        @NotBlank(message = "조치 메모는 필수입니다.")
        @Size(max = 1000, message = "조치 메모는 1000자 이하여야 합니다.")
        String resolutionNote,

        @NotBlank(message = "처리자는 필수입니다.")
        @Size(max = 100, message = "처리자는 100자 이하여야 합니다.")
        String actor
) {
}
