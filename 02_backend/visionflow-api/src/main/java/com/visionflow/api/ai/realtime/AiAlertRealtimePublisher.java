package com.visionflow.api.ai.realtime;

import com.visionflow.api.ai.dto.AiAlertResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Component;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Component
public class AiAlertRealtimePublisher {

    private static final Logger log = LoggerFactory.getLogger(
            AiAlertRealtimePublisher.class
    );

    private final SimpMessagingTemplate messagingTemplate;

    public AiAlertRealtimePublisher(
            SimpMessagingTemplate messagingTemplate
    ) {
        this.messagingTemplate = messagingTemplate;
    }

    public void publishAfterCommit(
            AiAlertRealtimeAction action,
            AiAlertResponse alert
    ) {
        AiAlertRealtimeMessage message =
                AiAlertRealtimeMessage.of(action, alert);

        Runnable publishTask = () -> {
            try {
                publishNow(message);
            } catch (RuntimeException error) {
                log.error(
                        "AI 경보 실시간 메시지 발행 실패: alertId={}, action={}",
                        alert.id(),
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

    private void publishNow(AiAlertRealtimeMessage message) {
        messagingTemplate.convertAndSend(
                "/topic/ai/alerts",
                message
        );

        messagingTemplate.convertAndSend(
                "/topic/drones/"
                        + message.alert().droneId()
                        + "/ai-alerts",
                message
        );
    }
}
