package com.visionflow.api.flight.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;
import java.time.Duration;
import java.time.LocalDateTime;

@Embeddable
public class FlightSessionPause {
    @Column(name = "paused_at", nullable = false)
    private LocalDateTime pausedAt;
    @Column(name = "resumed_at")
    private LocalDateTime resumedAt;
    protected FlightSessionPause() {}
    public FlightSessionPause(LocalDateTime pausedAt) { this.pausedAt = pausedAt; }
    public LocalDateTime getPausedAt() { return pausedAt; }
    public LocalDateTime getResumedAt() { return resumedAt; }
    public void resume(LocalDateTime at) {
        if (resumedAt == null) resumedAt = at.isBefore(pausedAt) ? pausedAt : at;
    }
    public double overlapSeconds(LocalDateTime from, LocalDateTime to) {
        // An open pause is displayed, but never excuses an unconfirmed communication gap.
        if (resumedAt == null) return 0;
        LocalDateTime start = pausedAt.isAfter(from) ? pausedAt : from;
        LocalDateTime end = resumedAt.isBefore(to) ? resumedAt : to;
        return end.isAfter(start) ? Duration.between(start, end).toMillis() / 1000.0 : 0;
    }
}
