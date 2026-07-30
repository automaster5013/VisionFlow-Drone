package com.visionflow.api.ai.repository;

import com.visionflow.api.ai.domain.AiDetection;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Collection;
import java.util.List;

public interface AiDetectionRepository
        extends JpaRepository<AiDetection, Long> {

    List<AiDetection> findAllByEventIdOrderByIdAsc(Long eventId);

    List<AiDetection> findAllByEventIdInOrderByEventIdAscIdAsc(
            Collection<Long> eventIds
    );
}
