package com.visionflow.api.incident.realtime;

import com.visionflow.api.incident.dto.IncidentResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Component;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Component
public class IncidentRealtimePublisher {

    private static final Logger log = LoggerFactory.getLogger(
            IncidentRealtimePublisher.class
    );

    private final SimpMessagingTemplate messagingTemplate;

    public IncidentRealtimePublisher(
            SimpMessagingTemplate messagingTemplate
    ) {
        this.messagingTemplate = messagingTemplate;
    }

    public void publishAfterCommit(
            IncidentRealtimeAction action,
            IncidentResponse incident
    ) {
        IncidentRealtimeMessage message =
                IncidentRealtimeMessage.of(action, incident);

        Runnable publishTask = () -> {
            try {
                publishNow(message);
            } catch (RuntimeException error) {
                log.error(
                        "Incident 실시간 메시지 발행 실패: "
                                + "incidentId={}, action={}",
                        incident.id(),
                        action,
                        error
                );
            }
        };

        if (
                TransactionSynchronizationManager
                        .isActualTransactionActive()
                        && TransactionSynchronizationManager
                        .isSynchronizationActive()
        ) {
            TransactionSynchronizationManager.registerSynchronization(
                    new TransactionSynchronization() {
                        @Override
                        public void afterCommit() {
                            publishTask.run();
                        }
                    }
            );
            return;
        }

        publishTask.run();
    }

    private void publishNow(IncidentRealtimeMessage message) {
        messagingTemplate.convertAndSend(
                "/topic/incidents",
                message
        );

        messagingTemplate.convertAndSend(
                "/topic/drones/"
                        + message.incident().droneId()
                        + "/incidents",
                message
        );
    }
}
