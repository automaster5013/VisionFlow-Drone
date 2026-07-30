package com.visionflow.api.maintenance.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record MaintenanceInspectionStartRequest(
        @NotBlank(message = "점검 담당자는 필수입니다.")
        @Size(max = 100, message = "점검 담당자는 100자 이하여야 합니다.")
        String assignee,

        @NotBlank(message = "처리자는 필수입니다.")
        @Size(max = 100, message = "처리자는 100자 이하여야 합니다.")
        String actor,

        @Size(max = 1000, message = "점검 시작 메모는 1000자 이하여야 합니다.")
        String note
) {
}
