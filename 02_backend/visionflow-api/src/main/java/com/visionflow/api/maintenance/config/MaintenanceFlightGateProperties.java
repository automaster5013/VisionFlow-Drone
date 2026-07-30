package com.visionflow.api.maintenance.config;

import com.visionflow.api.incident.domain.IncidentPriority;
import com.visionflow.api.maintenance.domain.MaintenanceFlightGateMode;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

@Component
@ConfigurationProperties(
        prefix = "visionflow.maintenance.flight-gate"
)
public class MaintenanceFlightGateProperties {

    private MaintenanceFlightGateMode mode =
            MaintenanceFlightGateMode.ADVISORY;
    private IncidentEscalation incident = new IncidentEscalation();

    public MaintenanceFlightGateMode getMode() {
        return mode;
    }

    public void setMode(MaintenanceFlightGateMode mode) {
        this.mode = mode == null
                ? MaintenanceFlightGateMode.ADVISORY
                : mode;
    }

    public IncidentEscalation getIncident() {
        return incident;
    }

    public void setIncident(IncidentEscalation incident) {
        this.incident = incident == null
                ? new IncidentEscalation()
                : incident;
    }

    public static class IncidentEscalation {

        private boolean enabled = true;
        private int threshold = 3;
        private int windowMinutes = 10;
        private IncidentPriority priority = IncidentPriority.HIGH;

        public boolean isEnabled() {
            return enabled;
        }

        public void setEnabled(boolean enabled) {
            this.enabled = enabled;
        }

        public int getThreshold() {
            return threshold;
        }

        public void setThreshold(int threshold) {
            this.threshold = Math.max(2, Math.min(threshold, 100));
        }

        public int getWindowMinutes() {
            return windowMinutes;
        }

        public void setWindowMinutes(int windowMinutes) {
            this.windowMinutes = Math.max(
                    1,
                    Math.min(windowMinutes, 1_440)
            );
        }

        public IncidentPriority getPriority() {
            return priority;
        }

        public void setPriority(IncidentPriority priority) {
            this.priority = priority == null
                    ? IncidentPriority.HIGH
                    : priority;
        }
    }
}
