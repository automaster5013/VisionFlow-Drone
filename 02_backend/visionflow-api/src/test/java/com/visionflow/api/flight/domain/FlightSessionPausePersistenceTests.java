package com.visionflow.api.flight.domain;

import com.visionflow.api.drone.domain.Drone;
import jakarta.persistence.EntityManager;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.transaction.annotation.Transactional;
import java.time.LocalDateTime;
import java.util.UUID;
import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
@Transactional
class FlightSessionPausePersistenceTests {
    @Autowired EntityManager em;

    @Test void pauseResumeSurvivesReloadAndTransactionRollsBack() {
        String id = UUID.randomUUID().toString();
        Drone drone = new Drone("pause-" + id.substring(0, 8), "pause test", null,
                null, null, null, null, null, null, 100, null);
        em.persist(drone);
        var start = LocalDateTime.now();
        var session = FlightSession.start(id, drone.getId(), "pause test", null,
                "presentation-simulator-001", start);
        em.persist(session);
        session.pause(start.plusSeconds(5));
        em.flush(); em.clear();
        session = em.find(FlightSession.class, id);
        assertEquals(1, session.getPauses().size());
        assertNull(session.getPauses().get(0).getResumedAt());
        session.resume(start.plusSeconds(25));
        em.flush(); em.clear();
        session = em.find(FlightSession.class, id);
        assertEquals(20, session.getPauses().get(0).overlapSeconds(start, start.plusSeconds(30)));
    }
}
