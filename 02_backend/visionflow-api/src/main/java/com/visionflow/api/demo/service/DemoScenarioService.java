package com.visionflow.api.demo.service;

import com.visionflow.api.ai.domain.AiAlert;
import com.visionflow.api.ai.domain.VideoSourceType;
import com.visionflow.api.ai.dto.AiDetectionRequest;
import com.visionflow.api.ai.dto.AiInferenceEventCreateRequest;
import com.visionflow.api.ai.dto.AiInferenceEventResponse;
import com.visionflow.api.ai.repository.AiAlertRepository;
import com.visionflow.api.ai.service.AiAlertService;
import com.visionflow.api.ai.service.AiInferenceEventService;
import com.visionflow.api.common.exception.ResourceNotFoundException;
import com.visionflow.api.demo.domain.DemoScenario;
import com.visionflow.api.demo.domain.DemoScenarioStage;
import com.visionflow.api.demo.dto.DemoScenarioResponse;
import com.visionflow.api.demo.dto.DemoScenarioStartRequest;
import com.visionflow.api.demo.repository.DemoScenarioRepository;
import com.visionflow.api.drone.domain.DroneTelemetrySource;
import com.visionflow.api.drone.dto.DroneTelemetryUpdateRequest;
import com.visionflow.api.drone.service.DroneService;
import com.visionflow.api.flight.dto.FlightSessionResponse;
import com.visionflow.api.flight.dto.FlightSessionStartRequest;
import com.visionflow.api.flight.service.FlightSessionManagementService;
import com.visionflow.api.incident.domain.Incident;
import com.visionflow.api.incident.domain.IncidentSourceType;
import com.visionflow.api.incident.dto.IncidentContextResponse;
import com.visionflow.api.incident.repository.IncidentRepository;
import com.visionflow.api.incident.service.IncidentContextService;
import com.visionflow.api.incident.service.IncidentSlaEscalationService;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;

import javax.imageio.ImageIO;
import java.awt.Color;
import java.awt.Font;
import java.awt.Graphics2D;
import java.awt.RenderingHints;
import java.awt.image.BufferedImage;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.math.BigDecimal;
import java.nio.file.Files;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.List;
import java.util.UUID;

@Service
public class DemoScenarioService {

    private static final String DEMO_DEVICE_ID =
            "visionflow-demo-console";
    private static final DateTimeFormatter SNAPSHOT_TIME_FORMAT =
            DateTimeFormatter.ofPattern("uuuu-MM-dd HH:mm:ss 'UTC'");

    private final DemoScenarioRepository scenarioRepository;
    private final FlightSessionManagementService flightSessionService;
    private final DroneService droneService;
    private final AiInferenceEventService inferenceEventService;
    private final AiAlertService alertService;
    private final AiAlertRepository alertRepository;
    private final IncidentRepository incidentRepository;
    private final IncidentContextService incidentContextService;
    private final IncidentSlaEscalationService escalationService;
    private final JdbcTemplate jdbcTemplate;

    public DemoScenarioService(
            DemoScenarioRepository scenarioRepository,
            FlightSessionManagementService flightSessionService,
            DroneService droneService,
            AiInferenceEventService inferenceEventService,
            AiAlertService alertService,
            AiAlertRepository alertRepository,
            IncidentRepository incidentRepository,
            IncidentContextService incidentContextService,
            IncidentSlaEscalationService escalationService,
            JdbcTemplate jdbcTemplate
    ) {
        this.scenarioRepository = scenarioRepository;
        this.flightSessionService = flightSessionService;
        this.droneService = droneService;
        this.inferenceEventService = inferenceEventService;
        this.alertService = alertService;
        this.alertRepository = alertRepository;
        this.incidentRepository = incidentRepository;
        this.incidentContextService = incidentContextService;
        this.escalationService = escalationService;
        this.jdbcTemplate = jdbcTemplate;
    }

    @Transactional
    public DemoScenarioResponse start(DemoScenarioStartRequest request) {
        FlightSessionResponse flightSession = flightSessionService.start(
                request.droneId(),
                new FlightSessionStartRequest(
                        "VisionFlow 발표 시연",
                        "가상 드론 텔레메트리와 YOLO 화재 탐지 통합 시나리오",
                        DEMO_DEVICE_ID
                )
        );

        createDemoTrack(
                request.droneId(),
                flightSession.sessionId(),
                request.latitude(),
                request.longitude()
        );

        DemoScenario scenario = DemoScenario.start(
                UUID.randomUUID().toString(),
                request.droneId(),
                flightSession.sessionId()
        );
        return toResponse(scenarioRepository.saveAndFlush(scenario));
    }

    @Transactional(readOnly = true)
    public DemoScenarioResponse find(String scenarioId) {
        return toResponse(findScenario(scenarioId));
    }

    @Transactional
    public DemoScenarioResponse detect(String scenarioId) {
        DemoScenario scenario = findScenarioForUpdate(scenarioId);
        requireStage(scenario, DemoScenarioStage.READY);
        Instant capturedAt = Instant.now();
        AiInferenceEventResponse event = inferenceEventService.create(
                new AiInferenceEventCreateRequest(
                        "visionflow-demo-" + scenario.getScenarioId(),
                        scenario.getFlightSessionId(),
                        VideoSourceType.DUMMY_VIDEO,
                        scenario.getDroneId(),
                        0L,
                        capturedAt,
                        new BigDecimal("18.4"),
                        1,
                        List.of(new AiDetectionRequest(
                                0,
                                "fire",
                                new BigDecimal("0.94"),
                                new BigDecimal("120"),
                                new BigDecimal("90"),
                                new BigDecimal("840"),
                                new BigDecimal("480")
                        ))
                )
        );

        inferenceEventService.attachSnapshot(
                event.id(),
                new ByteArrayMultipartFile(
                        "visionflow-demo-fire.jpg",
                        createDemoSnapshot(
                                scenario.getDroneId(),
                                scenario.getFlightSessionId(),
                                capturedAt
                        )
                )
        );

        AiAlert alert = alertRepository.findByEventId(event.id())
                .orElseThrow(() -> new ResourceNotFoundException(
                        "시연 AI 경보를 찾을 수 없습니다: " + event.id()
                ));
        Incident incident = incidentRepository
                .findBySourceTypeAndSourceId(
                        IncidentSourceType.AI_ALERT,
                        alert.getId()
                )
                .orElseThrow(() -> new ResourceNotFoundException(
                        "시연 Incident를 찾을 수 없습니다: "
                                + alert.getId()
                ));

        scenario.markDetected(event.id(), alert.getId(), incident.getId());
        return toResponse(scenarioRepository.saveAndFlush(scenario));
    }

    @Transactional
    public DemoScenarioResponse escalate(String scenarioId) {
        DemoScenario scenario = findScenarioForUpdate(scenarioId);
        requireStage(scenario, DemoScenarioStage.DETECTED);
        Long incidentId = requireIncidentId(scenario);
        LocalDateTime overdueAt = LocalDateTime.now(ZoneOffset.UTC)
                .minusSeconds(1);
        lockIncidentForDemoEscalation(incidentId);
        int updated = jdbcTemplate.update(
                """
                UPDATE incident
                SET sla_due_at = ?,
                    sla_breached_at = NULL,
                    escalation_level = 0
                WHERE id = ?
                  AND status IN ('OPEN', 'IN_PROGRESS')
                """,
                overdueAt,
                incidentId
        );

        if (updated != 1) {
            throw new IllegalArgumentException(
                    "SLA 초과 상태로 전환할 수 없는 Incident입니다: "
                            + incidentId
            );
        }

        escalationService.escalateIncidentIfOverdue(incidentId);
        scenario.markEscalated();
        return toResponse(scenarioRepository.saveAndFlush(scenario));
    }

    private void lockIncidentForDemoEscalation(Long incidentId) {
        Long lockedId = jdbcTemplate.query(
                "SELECT id FROM incident WHERE id = ? FOR UPDATE",
                resultSet -> resultSet.next()
                        ? resultSet.getLong("id")
                        : null,
                incidentId
        );
        if (lockedId == null) {
            throw new ResourceNotFoundException(
                    "시연 Incident를 찾을 수 없습니다: " + incidentId
            );
        }
    }

    @Transactional
    public DemoScenarioResponse resolve(String scenarioId) {
        DemoScenario scenario = findScenarioForUpdate(scenarioId);
        requireStage(scenario, DemoScenarioStage.ESCALATED);
        Long alertId = scenario.getAiAlertId();
        if (alertId == null) {
            throw new IllegalArgumentException(
                    "먼저 AI 탐지 단계를 실행해 주세요."
            );
        }

        alertService.resolve(
                alertId,
                "visionflow-demo-operator",
                "발표 시연 대응 완료"
        );
        scenario.markResolved();
        return toResponse(scenarioRepository.saveAndFlush(scenario));
    }

    @Transactional
    public DemoScenarioResponse complete(String scenarioId) {
        DemoScenario scenario = findScenarioForUpdate(scenarioId);
        requireStage(scenario, DemoScenarioStage.RESOLVED);
        flightSessionService.complete(
                scenario.getDroneId(),
                scenario.getFlightSessionId()
        );
        scenario.markCompleted();
        return toResponse(scenarioRepository.saveAndFlush(scenario));
    }

    private void createDemoTrack(
            Long droneId,
            String sessionId,
            BigDecimal latitude,
            BigDecimal longitude
    ) {
        LocalDateTime baseTime = LocalDateTime.now().minusSeconds(8);

        for (int index = 0; index < 5; index += 1) {
            BigDecimal offset = new BigDecimal("0.00015")
                    .multiply(BigDecimal.valueOf(index));
            droneService.updateTelemetry(
                    droneId,
                    new DroneTelemetryUpdateRequest(
                            latitude.add(offset),
                            longitude.add(offset),
                            BigDecimal.valueOf(30L + index * 3L),
                            96 - index,
                            BigDecimal.valueOf(45L + index * 8L),
                            BigDecimal.ZERO,
                            BigDecimal.ZERO,
                            new BigDecimal("4.5"),
                            new BigDecimal("2.0"),
                            new BigDecimal("3.0"),
                            DroneTelemetrySource.SIMULATOR,
                            DEMO_DEVICE_ID,
                            sessionId,
                            baseTime.plusSeconds(index * 2L)
                    )
            );
        }
    }

    private DemoScenario findScenario(String scenarioId) {
        String normalized = normalizeScenarioId(scenarioId);
        return scenarioRepository.findById(normalized)
                .orElseThrow(() -> new ResourceNotFoundException(
                        "시연 시나리오를 찾을 수 없습니다: " + normalized
                ));
    }

    private DemoScenario findScenarioForUpdate(String scenarioId) {
        String normalized = normalizeScenarioId(scenarioId);
        return scenarioRepository.findByIdForUpdate(normalized)
                .orElseThrow(() -> new ResourceNotFoundException(
                        "시연 시나리오를 찾을 수 없습니다: " + normalized
                ));
    }

    private String normalizeScenarioId(String scenarioId) {
        String normalized = scenarioId == null ? "" : scenarioId.trim();
        if (normalized.isEmpty() || normalized.length() > 36) {
            throw new IllegalArgumentException(
                    "시연 시나리오 ID는 1~36자여야 합니다."
            );
        }

        return normalized;
    }

    private Long requireIncidentId(DemoScenario scenario) {
        if (scenario.getIncidentId() == null) {
            throw new IllegalArgumentException(
                    "먼저 AI 탐지 단계를 실행해 주세요."
            );
        }
        return scenario.getIncidentId();
    }

    private void requireStage(
            DemoScenario scenario,
            DemoScenarioStage expected
    ) {
        if (scenario.getStage() != expected) {
            throw new IllegalArgumentException(
                    "현재 시연 단계에서는 실행할 수 없습니다. expected="
                            + expected
                            + ", actual="
                            + scenario.getStage()
            );
        }
    }

    private DemoScenarioResponse toResponse(DemoScenario scenario) {
        IncidentContextResponse incidentContext = null;
        if (scenario.getIncidentId() != null) {
            Incident incident = incidentRepository
                    .findById(scenario.getIncidentId())
                    .orElseThrow(() -> new ResourceNotFoundException(
                            "시연 Incident를 찾을 수 없습니다: "
                                    + scenario.getIncidentId()
                    ));
            incidentContext = incidentContextService.build(incident);
        }

        return new DemoScenarioResponse(
                scenario.getScenarioId(),
                scenario.getDroneId(),
                scenario.getFlightSessionId(),
                scenario.getAiEventId(),
                scenario.getAiAlertId(),
                scenario.getIncidentId(),
                scenario.getStage(),
                scenario.getLastMessage(),
                toInstant(scenario.getStartedAt()),
                toInstant(scenario.getUpdatedAt()),
                toInstant(scenario.getCompletedAt()),
                incidentContext
        );
    }

    private Instant toInstant(LocalDateTime value) {
        return value == null ? null : value.toInstant(ZoneOffset.UTC);
    }

    private byte[] createDemoSnapshot(
            Long droneId,
            String sessionId,
            Instant capturedAt
    ) {
        BufferedImage image = new BufferedImage(
                960,
                540,
                BufferedImage.TYPE_INT_RGB
        );
        Graphics2D graphics = image.createGraphics();

        try {
            graphics.setRenderingHint(
                    RenderingHints.KEY_ANTIALIASING,
                    RenderingHints.VALUE_ANTIALIAS_ON
            );
            graphics.setColor(new Color(18, 24, 38));
            graphics.fillRect(0, 0, 960, 540);
            graphics.setColor(new Color(239, 68, 68));
            graphics.fillRoundRect(80, 82, 800, 330, 36, 36);
            graphics.setColor(new Color(127, 29, 29));
            graphics.fillOval(570, 145, 190, 190);
            graphics.setColor(Color.WHITE);
            graphics.setFont(new Font("SansSerif", Font.BOLD, 38));
            graphics.drawString("VISIONFLOW AI DEMO", 120, 155);
            graphics.setFont(new Font("SansSerif", Font.BOLD, 58));
            graphics.drawString("FIRE DETECTED", 120, 240);
            graphics.setFont(new Font("SansSerif", Font.PLAIN, 24));
            graphics.drawString("Drone ID: " + droneId, 120, 302);
            graphics.drawString("Session: " + sessionId, 120, 342);
            graphics.drawString(
                    SNAPSHOT_TIME_FORMAT.format(
                            capturedAt.atZone(ZoneOffset.UTC)
                    ),
                    120,
                    382
            );
            graphics.setColor(new Color(251, 191, 36));
            graphics.setFont(new Font("SansSerif", Font.BOLD, 30));
            graphics.drawString("94%", 630, 255);
        } finally {
            graphics.dispose();
        }

        try (ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            if (!ImageIO.write(image, "jpg", output)) {
                throw new IllegalStateException(
                        "JPEG 이미지 인코더를 사용할 수 없습니다."
                );
            }
            return output.toByteArray();
        } catch (IOException error) {
            throw new IllegalStateException(
                    "시연 스냅샷 생성에 실패했습니다.",
                    error
            );
        }
    }

    private static final class ByteArrayMultipartFile
            implements MultipartFile {

        private final String originalFilename;
        private final byte[] bytes;

        private ByteArrayMultipartFile(
                String originalFilename,
                byte[] bytes
        ) {
            this.originalFilename = originalFilename;
            this.bytes = bytes.clone();
        }

        @Override
        public String getName() {
            return "snapshot";
        }

        @Override
        public String getOriginalFilename() {
            return originalFilename;
        }

        @Override
        public String getContentType() {
            return "image/jpeg";
        }

        @Override
        public boolean isEmpty() {
            return bytes.length == 0;
        }

        @Override
        public long getSize() {
            return bytes.length;
        }

        @Override
        public byte[] getBytes() {
            return bytes.clone();
        }

        @Override
        public InputStream getInputStream() {
            return new ByteArrayInputStream(bytes);
        }

        @Override
        public void transferTo(File destination) throws IOException {
            Files.write(destination.toPath(), bytes);
        }
    }
}
