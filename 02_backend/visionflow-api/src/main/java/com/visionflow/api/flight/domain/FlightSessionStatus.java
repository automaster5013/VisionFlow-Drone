package com.visionflow.api.flight.domain;

public enum FlightSessionStatus {
    READY,
    ACTIVE,
    COMPLETED,
    ABORTED;

    public boolean isTerminal() {
        return this == COMPLETED || this == ABORTED;
    }
}
