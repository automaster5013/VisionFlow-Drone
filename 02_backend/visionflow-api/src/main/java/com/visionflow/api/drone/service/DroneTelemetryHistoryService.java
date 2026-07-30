package com.visionflow.api.drone.service;

import com.visionflow.api.drone.domain.Drone;
import com.visionflow.api.drone.domain.DroneTelemetryHistory;
import com.visionflow.api.drone.dto.DroneTelemetryHistoryResponse;
import com.visionflow.api.drone.repository.DroneTelemetryHistoryRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.Collections;
import java.util.List;

@Service
@RequiredArgsConstructor
public class DroneTelemetryHistoryService {

    private static final int DEFAULT_LIMIT = 500;
    private static final int MAX_LIMIT = 5_000;

    private final DroneTelemetryHistoryRepository historyRepository;

    @Transactional
    public void record(
            Drone drone,
            LocalDateTime recordedAt
    ) {
        DroneTelemetryHistory history =
                DroneTelemetryHistory.from(
                        drone,
                        recordedAt
                );

        historyRepository.save(history);
    }

    @Transactional(readOnly = true)
    public List<DroneTelemetryHistoryResponse> getHistory(
            Long droneId,
            LocalDateTime from,
            LocalDateTime to,
            Integer requestedLimit
    ) {
        int limit = normalizeLimit(requestedLimit);
        Pageable pageable = PageRequest.of(0, limit);

        List<DroneTelemetryHistory> histories;

        if (from == null && to == null) {
            histories =
                    historyRepository
                            .findByDroneIdOrderByRecordedAtDesc(
                                    droneId,
                                    pageable
                            );

            // DB에서는 최신순으로 제한하고,
            // 지도에서는 시간순으로 사용하도록 다시 정렬
            Collections.reverse(histories);
        } else {
            LocalDateTime rangeStart =
                    from != null
                            ? from
                            : LocalDateTime.of(
                            1970,
                            1,
                            1,
                            0,
                            0
                    );

            LocalDateTime rangeEnd =
                    to != null
                            ? to
                            : LocalDateTime.now();

            if (rangeStart.isAfter(rangeEnd)) {
                throw new IllegalArgumentException(
                        "조회 시작 시각은 종료 시각보다 늦을 수 없습니다."
                );
            }

            histories =
                    historyRepository
                            .findByDroneIdAndRecordedAtBetweenOrderByRecordedAtAsc(
                                    droneId,
                                    rangeStart,
                                    rangeEnd,
                                    pageable
                            );
        }

        return histories.stream()
                .map(DroneTelemetryHistoryResponse::from)
                .toList();
    }

    private int normalizeLimit(Integer requestedLimit) {
        if (requestedLimit == null) {
            return DEFAULT_LIMIT;
        }

        return Math.max(
                1,
                Math.min(requestedLimit, MAX_LIMIT)
        );
    }
}