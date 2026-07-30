package com.visionflow.api.drone.realtime;

import com.visionflow.api.drone.dto.DroneResponse;
import lombok.RequiredArgsConstructor;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Component;

@Component
@RequiredArgsConstructor
public class DroneRealtimePublisher {

    private final SimpMessagingTemplate messagingTemplate;

    public void publish(DroneResponse drone) {
        // 기존: 특정 드론 상세 화면 구독용
        messagingTemplate.convertAndSend(
                "/topic/drones/" + drone.id() + "/telemetry",
                drone
        );

        // 추가: 전체 드론 목록 및 관제 지도 구독용
        messagingTemplate.convertAndSend(
                "/topic/drones/telemetry",
                drone
        );
    }
}