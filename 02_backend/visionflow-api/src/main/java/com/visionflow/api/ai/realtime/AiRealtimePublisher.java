package com.visionflow.api.ai.realtime;

import com.visionflow.api.ai.dto.AiInferenceEventResponse;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Component;

@Component
public class AiRealtimePublisher {

    private final SimpMessagingTemplate messagingTemplate;

    public AiRealtimePublisher(
            SimpMessagingTemplate messagingTemplate
    ) {
        this.messagingTemplate = messagingTemplate;
    }

    public void publish(AiInferenceEventResponse event) {
        messagingTemplate.convertAndSend(
                "/topic/ai/events",
                event
        );

        messagingTemplate.convertAndSend(
                "/topic/drones/" + event.droneId() + "/ai-events",
                event
        );
    }
}
