package com.visionflow.api.audit.service;

import com.visionflow.api.audit.domain.AuditAction;
import com.visionflow.api.audit.domain.AuditEntityType;
import com.visionflow.api.audit.domain.AuditLog;
import com.visionflow.api.audit.dto.AuditLogExportResult;
import com.visionflow.api.audit.dto.AuditLogPageResponse;
import com.visionflow.api.audit.dto.AuditLogResponse;
import com.visionflow.api.audit.repository.AuditLogRepository;
import com.visionflow.api.common.security.OperatorCredentialRegistry;
import com.visionflow.api.common.security.OperatorPrincipal;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.json.JsonMapper;

import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.List;
import java.util.Map;
import java.util.UUID;

@Service
public class AuditLogService {

    private static final String ACTOR_HEADER = "X-VisionFlow-Actor";
    private static final String TRACE_HEADER = "X-Request-Id";
    private static final String LOCAL_ACTOR = "local-operator";
    private static final String SYSTEM_ACTOR = "system";
    private static final int MAX_EXPORT_ROWS = 5_000;
    private static final DateTimeFormatter EXPORT_FILE_TIME_FORMAT =
            DateTimeFormatter.ofPattern("uuuuMMdd'T'HHmmss'Z'")
                    .withZone(ZoneOffset.UTC);

    private final AuditLogRepository auditLogRepository;
    private final JsonMapper jsonMapper;
    private final OperatorCredentialRegistry credentialRegistry;

    public AuditLogService(
            AuditLogRepository auditLogRepository,
            JsonMapper jsonMapper,
            OperatorCredentialRegistry credentialRegistry
    ) {
        this.auditLogRepository = auditLogRepository;
        this.jsonMapper = jsonMapper;
        this.credentialRegistry = credentialRegistry;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public AuditLogResponse record(
            AuditAction action,
            AuditEntityType entityType,
            Object entityId,
            String summary,
            Map<String, ?> details
    ) {
        return record(action, entityType, entityId, summary, details, null);
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public AuditLogResponse record(
            AuditAction action,
            AuditEntityType entityType,
            Object entityId,
            String summary,
            Map<String, ?> details,
            String explicitActor
    ) {
        return persist(
                action,
                entityType,
                entityId,
                summary,
                details,
                resolveRequestContext(explicitActor, false)
        );
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public AuditLogResponse recordAuthenticationEvent(
            AuditAction action,
            Object entityId,
            String summary,
            Map<String, ?> details,
            String actor
    ) {
        return persist(
                action,
                AuditEntityType.OPERATOR_SESSION,
                entityId,
                summary,
                details,
                resolveRequestContext(actor, true)
        );
    }

    private AuditLogResponse persist(
            AuditAction action,
            AuditEntityType entityType,
            Object entityId,
            String summary,
            Map<String, ?> details,
            RequestAuditContext context
    ) {
        LocalDateTime occurredAt = LocalDateTime.now(ZoneOffset.UTC);
        AuditLog auditLog = AuditLog.create(
                occurredAt,
                context.actor(),
                requireValue(action, "감사 작업"),
                requireValue(entityType, "감사 대상 유형"),
                normalizeRequired(
                        requireValue(entityId, "감사 대상 ID").toString(),
                        100,
                        "감사 대상 ID"
                ),
                normalizeRequired(summary, 255, "감사 요약"),
                serializeDetails(details),
                context.requestMethod(),
                context.requestPath(),
                context.traceId()
        );
        return AuditLogResponse.from(auditLogRepository.saveAndFlush(auditLog));
    }

    @Transactional(readOnly = true)
    public AuditLogPageResponse find(
            AuditAction action,
            AuditEntityType entityType,
            String entityId,
            String actor,
            Instant from,
            Instant to,
            int page,
            int size
    ) {
        validatePeriod(from, to);

        PageRequest pageable = PageRequest.of(
                page,
                size,
                newestFirst()
        );
        Page<AuditLogResponse> result = auditLogRepository.search(
                        action,
                        entityType,
                        normalizeOptional(entityId, 100, "감사 대상 ID"),
                        normalizeOptional(actor, 100, "감사 처리자"),
                        toUtcDateTime(from),
                        toUtcDateTime(to),
                        pageable
                )
                .map(AuditLogResponse::from);
        return AuditLogPageResponse.from(result);
    }

    @Transactional(readOnly = true)
    public AuditLogExportResult exportCsv(
            AuditAction action,
            AuditEntityType entityType,
            String entityId,
            String actor,
            Instant from,
            Instant to,
            int limit
    ) {
        validatePeriod(from, to);
        if (limit < 1 || limit > MAX_EXPORT_ROWS) {
            throw new IllegalArgumentException(
                    "감사 로그 CSV 내보내기 개수는 1~5000이어야 합니다."
            );
        }

        Page<AuditLog> result = auditLogRepository.search(
                action,
                entityType,
                normalizeOptional(entityId, 100, "감사 대상 ID"),
                normalizeOptional(actor, 100, "감사 처리자"),
                toUtcDateTime(from),
                toUtcDateTime(to),
                PageRequest.of(0, limit, newestFirst())
        );
        byte[] content = buildCsv(result.getContent());
        String filename = "visionflow-audit-log-"
                + EXPORT_FILE_TIME_FORMAT.format(Instant.now())
                + ".csv";
        return new AuditLogExportResult(
                content,
                filename,
                result.getNumberOfElements(),
                result.getTotalElements()
        );
    }

    private byte[] buildCsv(List<AuditLog> rows) {
        StringBuilder csv = new StringBuilder(4_096);
        appendCsvRow(
                csv,
                "id",
                "occurredAt",
                "actor",
                "action",
                "entityType",
                "entityId",
                "summary",
                "detailsJson",
                "requestMethod",
                "requestPath",
                "traceId"
        );
        for (AuditLog row : rows) {
            appendCsvRow(
                    csv,
                    String.valueOf(row.getId()),
                    row.getOccurredAt().toInstant(ZoneOffset.UTC).toString(),
                    row.getActor(),
                    row.getAction().name(),
                    row.getEntityType().name(),
                    row.getEntityId(),
                    row.getSummary(),
                    row.getDetailsJson(),
                    row.getRequestMethod(),
                    row.getRequestPath(),
                    row.getTraceId()
            );
        }
        return ("\uFEFF" + csv).getBytes(StandardCharsets.UTF_8);
    }

    private void appendCsvRow(StringBuilder csv, String... values) {
        for (int index = 0; index < values.length; index++) {
            if (index > 0) {
                csv.append(',');
            }
            csv.append(csvCell(values[index]));
        }
        csv.append("\r\n");
    }

    private String csvCell(String value) {
        String safeValue = protectSpreadsheetFormula(value == null ? "" : value);
        return '"' + safeValue.replace("\"", "\"\"") + '"';
    }

    private String protectSpreadsheetFormula(String value) {
        int firstVisibleIndex = 0;
        while (
                firstVisibleIndex < value.length()
                        && Character.isWhitespace(value.charAt(firstVisibleIndex))
        ) {
            firstVisibleIndex++;
        }
        if (firstVisibleIndex >= value.length()) {
            return value;
        }
        char firstVisible = value.charAt(firstVisibleIndex);
        return firstVisible == '='
                || firstVisible == '+'
                || firstVisible == '-'
                || firstVisible == '@'
                ? "'" + value
                : value;
    }

    private Sort newestFirst() {
        return Sort.by(Sort.Direction.DESC, "occurredAt")
                .and(Sort.by(Sort.Direction.DESC, "id"));
    }

    private void validatePeriod(Instant from, Instant to) {
        if (from != null && to != null && from.isAfter(to)) {
            throw new IllegalArgumentException(
                    "감사 로그 시작 시각은 종료 시각보다 늦을 수 없습니다."
            );
        }
    }

    private RequestAuditContext resolveRequestContext(
            String explicitActor,
            boolean trustedActorOverride
    ) {
        ServletRequestAttributes attributes = RequestContextHolder.getRequestAttributes()
                instanceof ServletRequestAttributes servletAttributes
                ? servletAttributes
                : null;
        HttpServletRequest request = attributes == null ? null : attributes.getRequest();
        String actorCandidate = authenticatedActor();
        if (actorCandidate == null && trustedActorOverride) {
            actorCandidate = explicitActor;
        }
        if (actorCandidate == null && !credentialRegistry.isEnabled()) {
            actorCandidate = explicitActor;
            if (actorCandidate == null && request != null) {
                actorCandidate = request.getHeader(ACTOR_HEADER);
            }
        }
        String actor = normalizeActor(
                actorCandidate,
                request == null || credentialRegistry.isEnabled()
                        ? SYSTEM_ACTOR
                        : LOCAL_ACTOR
        );
        String traceCandidate = request == null ? null : request.getHeader(TRACE_HEADER);
        String traceId = normalizeTraceId(traceCandidate);
        String method = request == null ? null : normalizeOptional(
                request.getMethod(),
                10,
                "HTTP 메서드"
        );
        String path = request == null ? null : normalizeOptional(
                request.getRequestURI(),
                500,
                "요청 경로"
        );
        return new RequestAuditContext(actor, method, path, traceId);
    }

    private String authenticatedActor() {
        Authentication authentication = SecurityContextHolder
                .getContext()
                .getAuthentication();
        if (
                authentication != null
                        && authentication.isAuthenticated()
                        && authentication.getPrincipal() instanceof OperatorPrincipal principal
        ) {
            return principal.username();
        }
        return null;
    }

    private String serializeDetails(Map<String, ?> details) {
        if (details == null || details.isEmpty()) {
            return null;
        }
        try {
            String serialized = jsonMapper.writeValueAsString(details);
            if (serialized.length() > 10_000) {
                throw new IllegalArgumentException("감사 상세 정보는 10000자 이하여야 합니다.");
            }
            return serialized;
        } catch (JacksonException exception) {
            throw new IllegalArgumentException("감사 상세 정보를 JSON으로 변환할 수 없습니다.", exception);
        }
    }

    private String normalizeActor(String value, String defaultValue) {
        String candidate = value == null || value.isBlank() ? defaultValue : value;
        return normalizeRequired(candidate, 100, "감사 처리자");
    }

    private String normalizeTraceId(String value) {
        if (value == null || value.isBlank()) {
            return UUID.randomUUID().toString();
        }
        String normalized = value.trim();
        if (normalized.length() > 64 || !normalized.matches("[A-Za-z0-9._:-]+")) {
            return UUID.randomUUID().toString();
        }
        return normalized;
    }

    private String normalizeRequired(String value, int maximumLength, String fieldName) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(fieldName + "는 필수입니다.");
        }
        String normalized = value.trim();
        if (normalized.length() > maximumLength) {
            throw new IllegalArgumentException(fieldName + "는 " + maximumLength + "자 이하여야 합니다.");
        }
        return normalized;
    }

    private String normalizeOptional(String value, int maximumLength, String fieldName) {
        if (value == null || value.isBlank()) {
            return null;
        }
        return normalizeRequired(value, maximumLength, fieldName);
    }

    private LocalDateTime toUtcDateTime(Instant value) {
        return value == null ? null : LocalDateTime.ofInstant(value, ZoneOffset.UTC);
    }

    private <T> T requireValue(T value, String fieldName) {
        if (value == null) {
            throw new IllegalArgumentException(fieldName + "는 필수입니다.");
        }
        return value;
    }

    private record RequestAuditContext(
            String actor,
            String requestMethod,
            String requestPath,
            String traceId
    ) {
    }
}
