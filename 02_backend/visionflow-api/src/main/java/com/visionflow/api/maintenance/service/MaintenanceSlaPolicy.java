package com.visionflow.api.maintenance.service;

import com.visionflow.api.maintenance.domain.MaintenanceSlaStatus;
import com.visionflow.api.maintenance.domain.MaintenanceWorkOrder;
import com.visionflow.api.maintenance.domain.MaintenanceWorkOrderStatus;

import java.time.Duration;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;

public final class MaintenanceSlaPolicy {

    public static final long OPEN_SLA_MINUTES = 120L;
    public static final long IN_PROGRESS_SLA_MINUTES = 240L;
    public static final long DUE_SOON_MINUTES = 30L;

    private MaintenanceSlaPolicy() {
    }

    public static Evaluation evaluate(
            MaintenanceWorkOrder workOrder,
            Instant evaluatedAt
    ) {
        if (
                workOrder == null
                        || workOrder.getStatus()
                        == MaintenanceWorkOrderStatus.COMPLETED
                        || workOrder.getStatus()
                        == MaintenanceWorkOrderStatus.GROUNDED
        ) {
            return Evaluation.notApplicable();
        }

        LocalDateTime startedAt;
        long limitMinutes;
        if (
                workOrder.getStatus()
                        == MaintenanceWorkOrderStatus.IN_PROGRESS
        ) {
            startedAt = workOrder.getStartedAt() == null
                    ? workOrder.getOpenedAt()
                    : workOrder.getStartedAt();
            limitMinutes = IN_PROGRESS_SLA_MINUTES;
        } else {
            startedAt = workOrder.getOpenedAt();
            limitMinutes = OPEN_SLA_MINUTES;
        }
        if (startedAt == null) {
            return Evaluation.notApplicable();
        }

        Instant dueAt = startedAt
                .toInstant(ZoneOffset.UTC)
                .plusSeconds(limitMinutes * 60L);
        if (evaluatedAt.isAfter(dueAt)) {
            return new Evaluation(
                    MaintenanceSlaStatus.OVERDUE,
                    dueAt,
                    0L,
                    Duration.between(dueAt, evaluatedAt).toMinutes()
            );
        }

        long remaining = Duration.between(
                evaluatedAt,
                dueAt
        ).toMinutes();
        return new Evaluation(
                remaining <= DUE_SOON_MINUTES
                        ? MaintenanceSlaStatus.DUE_SOON
                        : MaintenanceSlaStatus.ON_TRACK,
                dueAt,
                remaining,
                0L
        );
    }

    public record Evaluation(
            MaintenanceSlaStatus status,
            Instant dueAt,
            Long remainingMinutes,
            Long overdueMinutes
    ) {
        static Evaluation notApplicable() {
            return new Evaluation(
                    MaintenanceSlaStatus.NOT_APPLICABLE,
                    null,
                    null,
                    null
            );
        }
    }
}
