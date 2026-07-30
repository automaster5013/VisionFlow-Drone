package com.visionflow.api.maintenance.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

@Component
@ConfigurationProperties(prefix = "visionflow.maintenance.sla")
public class MaintenanceSlaAutomationProperties {

    private boolean automationEnabled = true;
    private long initialDelayMs = 15_000L;
    private long scanDelayMs = 30_000L;

    public boolean isAutomationEnabled() {
        return automationEnabled;
    }

    public void setAutomationEnabled(boolean automationEnabled) {
        this.automationEnabled = automationEnabled;
    }

    public long getInitialDelayMs() {
        return initialDelayMs;
    }

    public void setInitialDelayMs(long initialDelayMs) {
        this.initialDelayMs = positive(
                initialDelayMs,
                "initial-delay-ms"
        );
    }

    public long getScanDelayMs() {
        return scanDelayMs;
    }

    public void setScanDelayMs(long scanDelayMs) {
        this.scanDelayMs = positive(scanDelayMs, "scan-delay-ms");
    }

    private long positive(long value, String property) {
        if (value <= 0L) {
            throw new IllegalArgumentException(
                    "visionflow.maintenance.sla."
                            + property
                            + "는 0보다 커야 합니다."
            );
        }
        return value;
    }
}
