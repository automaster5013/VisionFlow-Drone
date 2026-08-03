package com.visionflow.api.maintenance.repository;

import com.visionflow.api.maintenance.domain.MaintenanceWorkOrder;
import com.visionflow.api.maintenance.domain.MaintenanceWorkOrderStatus;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import jakarta.persistence.LockModeType;

import java.time.LocalDateTime;
import java.util.Collection;
import java.util.List;
import java.util.Optional;

public interface MaintenanceWorkOrderRepository
        extends JpaRepository<MaintenanceWorkOrder, Long> {

    Optional<MaintenanceWorkOrder> findByIncidentId(Long incidentId);

    Optional<MaintenanceWorkOrder>
    findFirstByDroneIdOrderByUpdatedAtDescIdDesc(Long droneId);

    @Query("""
            SELECT workOrder
            FROM MaintenanceWorkOrder workOrder
            WHERE NOT EXISTS (
                SELECT newer.id
                FROM MaintenanceWorkOrder newer
                WHERE newer.droneId = workOrder.droneId
                  AND (
                        newer.updatedAt > workOrder.updatedAt
                        OR (
                            newer.updatedAt = workOrder.updatedAt
                            AND newer.id > workOrder.id
                        )
                  )
            )
            ORDER BY workOrder.updatedAt DESC, workOrder.id DESC
            """)
    List<MaintenanceWorkOrder> findLatestForAllDrones();

    @Query("""
            SELECT workOrder.id
            FROM MaintenanceWorkOrder workOrder
            WHERE workOrder.status IN :statuses
            ORDER BY workOrder.openedAt ASC, workOrder.id ASC
            """)
    List<Long> findActiveIdsForSlaEvaluation(
            @Param("statuses")
            Collection<MaintenanceWorkOrderStatus> statuses
    );

    @Query("""
            SELECT workOrder.incidentId
            FROM MaintenanceWorkOrder workOrder
            WHERE workOrder.id = :id
            """)
    Optional<Long> findIncidentIdById(@Param("id") Long id);

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("""
            SELECT workOrder
            FROM MaintenanceWorkOrder workOrder
            WHERE workOrder.id = :id
            """)
    Optional<MaintenanceWorkOrder> findByIdForUpdate(
            @Param("id") Long id
    );

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("""
            SELECT workOrder
            FROM MaintenanceWorkOrder workOrder
            WHERE workOrder.incidentId = :incidentId
            """)
    Optional<MaintenanceWorkOrder> findByIncidentIdForUpdate(
            @Param("incidentId") Long incidentId
    );

    @Query("""
            SELECT workOrder
            FROM MaintenanceWorkOrder workOrder
            WHERE (
                    :droneId IS NULL
                    OR workOrder.droneId = :droneId
                  )
              AND (
                    :status IS NULL
                    OR workOrder.status = :status
                  )
            ORDER BY workOrder.updatedAt DESC, workOrder.id DESC
            """)
    List<MaintenanceWorkOrder> findWorkOrders(
            @Param("droneId") Long droneId,
            @Param("status") MaintenanceWorkOrderStatus status,
            Pageable pageable
    );

    List<MaintenanceWorkOrder>
    findAllByOpenedAtGreaterThanEqualOrderByOpenedAtDescIdDesc(
            LocalDateTime openedAt
    );
}
