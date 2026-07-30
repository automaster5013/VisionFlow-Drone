package com.visionflow.api.audit.config;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;
import org.springframework.validation.annotation.Validated;

@Validated
@Component
@ConfigurationProperties(prefix = "visionflow.audit.retention")
public class AuditRetentionProperties {

    private boolean enabled = false;

    private boolean archiveConfirmed = false;

    @Min(1)
    @Max(3650)
    private int days = 90;

    @Min(1)
    @Max(5000)
    private int batchSize = 1000;

    @NotBlank
    private String cron = "0 30 3 * * *";

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public int getDays() {
        return days;
    }

    public boolean isArchiveConfirmed() {
        return archiveConfirmed;
    }

    public void setArchiveConfirmed(boolean archiveConfirmed) {
        this.archiveConfirmed = archiveConfirmed;
    }

    public void setDays(int days) {
        this.days = days;
    }

    public int getBatchSize() {
        return batchSize;
    }

    public void setBatchSize(int batchSize) {
        this.batchSize = batchSize;
    }

    public String getCron() {
        return cron;
    }

    public void setCron(String cron) {
        this.cron = cron;
    }
}
