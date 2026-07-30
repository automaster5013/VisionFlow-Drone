package com.visionflow.api.maintenance.repository;

import com.visionflow.api.maintenance.domain.MaintenanceWorkOrderHistory;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface MaintenanceWorkOrderHistoryRepository
        extends JpaRepository<MaintenanceWorkOrderHistory, Long> {

    List<MaintenanceWorkOrderHistory>
    findAllByWorkOrderIdOrderByCreatedAtAscIdAsc(Long workOrderId);
}
