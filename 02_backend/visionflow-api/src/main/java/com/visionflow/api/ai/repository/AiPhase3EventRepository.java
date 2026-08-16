package com.visionflow.api.ai.repository;

import com.visionflow.api.ai.domain.AiPhase3Event;
import jakarta.persistence.LockModeType;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.Optional;

public interface AiPhase3EventRepository
        extends JpaRepository<AiPhase3Event, Long> {

    Optional<AiPhase3Event> findByEventKey(String eventKey);

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("""
            SELECT event
            FROM AiPhase3Event event
            WHERE event.eventKey = :eventKey
            """)
    Optional<AiPhase3Event> findByEventKeyForUpdate(
            @Param("eventKey") String eventKey
    );
}