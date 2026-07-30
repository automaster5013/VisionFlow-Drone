package com.visionflow.api.geofence.realtime;

import com.visionflow.api.geofence.dto.GeofenceEventResponse;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Component;

@Component
public class GeofenceRealtimePublisher {

    private final SimpMessagingTemplate messagingTemplate;

    public GeofenceRealtimePublisher(
            SimpMessagingTemplate messagingTemplate
    ) {
        this.messagingTemplate = messagingTemplate;
    }

    public void publish(GeofenceEventResponse event) {
        messagingTemplate.convertAndSend(
                "/topic/geofences/events",
                event
        );

        messagingTemplate.convertAndSend(
                "/topic/drones/" + event.droneId() + "/geofence-events",
                event
        );
    }
}