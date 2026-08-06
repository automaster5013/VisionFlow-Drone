package com.visionflow.api.common.config;

import java.util.Arrays;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfig
        implements WebSocketMessageBrokerConfigurer {

    private final String[] allowedOriginPatterns;

    public WebSocketConfig(
            @Value("${visionflow.websocket.allowed-origin-patterns:"
                    + "http://localhost:3000,"
                    + "http://127.0.0.1:3000,"
                    + "https://localhost:3443,"
                    + "https://127.0.0.1:3443}")
            String[] allowedOriginPatterns
    ) {
        this.allowedOriginPatterns = Arrays.stream(allowedOriginPatterns)
                .map(String::trim)
                .filter(pattern -> !pattern.isEmpty())
                .toArray(String[]::new);
    }

    @Override
    public void configureMessageBroker(
            MessageBrokerRegistry registry
    ) {
        /*
         * 서버가 클라이언트에게 방송하는 목적지입니다.
         *
         * 예:
         * /topic/drones/1/telemetry
         */
        registry.enableSimpleBroker(
                "/topic",
                "/queue"
        );

        /*
         * 클라이언트가 서버의 @MessageMapping 메서드로
         * 메시지를 보낼 때 사용할 접두사입니다.
         *
         * 현재 단계에서는 서버 수신 메시지를 사용하지 않지만
         * 향후 드론 제어 명령에 사용할 수 있습니다.
         */
        registry.setApplicationDestinationPrefixes("/app");
    }

    @Override
    public void registerStompEndpoints(
            StompEndpointRegistry registry
    ) {
        registry
                .addEndpoint("/ws")
                .setAllowedOriginPatterns(allowedOriginPatterns);
    }
}
