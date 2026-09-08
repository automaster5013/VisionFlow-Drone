package com.visionflow.api.flight.domain;
import org.junit.jupiter.api.Test;
import java.time.LocalDateTime;
import static org.junit.jupiter.api.Assertions.*;

class FlightSessionPauseTests {
    private final LocalDateTime start = LocalDateTime.of(2026, 9, 9, 10, 0);
    private FlightSession session(String device) {
        return FlightSession.start("session", 3L, "demo", null, device, start);
    }
    @Test void retriesAreIdempotentAndCompletionClosesPause() {
        var session = session("presentation-simulator-001");
        session.pause(start.plusSeconds(5)); session.pause(start.plusSeconds(8));
        assertEquals(1, session.getPauses().size());
        session.resume(start.plusSeconds(20)); session.resume(start.plusSeconds(25));
        assertEquals(start.plusSeconds(20), session.getPauses().get(0).getResumedAt());
        session.pause(start.plusSeconds(30)); session.complete(start.plusSeconds(40));
        assertEquals(start.plusSeconds(40), session.getPauses().get(1).getResumedAt());
        assertThrows(IllegalArgumentException.class, () -> session.pause(start.plusSeconds(45)));
    }
    @Test void realFlightCannotBeExcluded() {
        assertThrows(IllegalArgumentException.class, () -> session("phone").pause(start));
    }
    @Test void onlyConfirmedOverlapIsExcluded() {
        var pause = new FlightSessionPause(start.plusSeconds(5));
        assertEquals(0, pause.overlapSeconds(start, start.plusSeconds(30)));
        pause.resume(start.plusSeconds(20));
        assertEquals(15, pause.overlapSeconds(start, start.plusSeconds(30)));
        assertEquals(3, pause.overlapSeconds(start.plusSeconds(17), start.plusSeconds(23)));
        assertEquals(0, pause.overlapSeconds(start.plusSeconds(21), start.plusSeconds(30)));
    }
}
