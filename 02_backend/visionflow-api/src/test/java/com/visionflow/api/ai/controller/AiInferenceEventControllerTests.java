package com.visionflow.api.ai.controller;

import com.visionflow.api.ai.domain.VideoSourceType;
import com.visionflow.api.ai.dto.AiInferenceEventResponse;
import com.visionflow.api.ai.service.AiInferenceEventService;
import com.visionflow.api.audit.domain.AuditAction;
import com.visionflow.api.audit.domain.AuditEntityType;
import com.visionflow.api.audit.service.AuditLogService;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class AiInferenceEventControllerTests {

    @Test
    void manualOperatorUploadRecordsManualPrivacyAudit() {
        AiInferenceEventService eventService = mock(AiInferenceEventService.class);
        AuditLogService auditLogService = mock(AuditLogService.class);
        AiInferenceEventController controller =
                new AiInferenceEventController(eventService, auditLogService);
        MockMultipartFile file = jpeg();
        AiInferenceEventResponse stored = storedResponse();
        when(eventService.attachSnapshot(141587L, file)).thenReturn(stored);

        var authentication = new UsernamePasswordAuthenticationToken(
                "operator",
                null,
                List.of(new SimpleGrantedAuthority("ROLE_OPERATOR"))
        );

        assertThat(
                controller.uploadSnapshot(
                        141587L,
                        file,
                        authentication
                )
        ).isSameAs(stored);

        @SuppressWarnings("rawtypes")
        ArgumentCaptor<Map> detailsCaptor = ArgumentCaptor.forClass(Map.class);
        verify(auditLogService).record(
                eq(AuditAction.PRIVACY_SNAPSHOT_STORED),
                eq(AuditEntityType.AI_INFERENCE_EVENT),
                eq(141587L),
                eq("AI 이벤트 개인정보 스냅샷 저장"),
                detailsCaptor.capture()
        );

        Map<?, ?> details = detailsCaptor.getValue();
        assertThat(details.get("storageMode")).isEqualTo("MANUAL_OPERATOR");
        assertThat(details.get("snapshotSizeBytes")).isEqualTo(4L);
        assertThat(details.containsKey("fileName")).isFalse();
        assertThat(details.containsKey("filePath")).isFalse();
        assertThat(details.containsKey("snapshotUrl")).isFalse();
        assertThat(details.containsKey("bytes")).isFalse();
    }

    @Test
    void aiInternalUploadRecordsMachineStorageMode() {
        AiInferenceEventService eventService = mock(AiInferenceEventService.class);
        AuditLogService auditLogService = mock(AuditLogService.class);
        AiInferenceEventController controller =
                new AiInferenceEventController(eventService, auditLogService);
        MockMultipartFile file = jpeg();
        AiInferenceEventResponse stored = storedResponse();
        when(eventService.attachSnapshot(141587L, file)).thenReturn(stored);

        var authentication = new UsernamePasswordAuthenticationToken(
                "visionflow-ai",
                null,
                List.of(new SimpleGrantedAuthority("ROLE_AI_INTERNAL"))
        );

        assertThat(
                controller.uploadSnapshot(
                        141587L,
                        file,
                        authentication
                )
        ).isSameAs(stored);

        @SuppressWarnings("rawtypes")
        ArgumentCaptor<Map> detailsCaptor = ArgumentCaptor.forClass(Map.class);
        verify(auditLogService).record(
                eq(AuditAction.PRIVACY_SNAPSHOT_STORED),
                eq(AuditEntityType.AI_INFERENCE_EVENT),
                eq(141587L),
                eq("AI 이벤트 개인정보 스냅샷 저장"),
                detailsCaptor.capture()
        );

        assertThat(detailsCaptor.getValue().get("storageMode"))
                .isEqualTo("AI_INTERNAL");
    }

    private MockMultipartFile jpeg() {
        return new MockMultipartFile(
                "file",
                "synthetic.jpg",
                "image/jpeg",
                new byte[] {
                        (byte) 0xFF,
                        (byte) 0xD8,
                        (byte) 0xFF,
                        (byte) 0xD9
                }
        );
    }

    private AiInferenceEventResponse storedResponse() {
        Instant now = Instant.parse("2026-08-22T08:00:00Z");

        return new AiInferenceEventResponse(
                141587L,
                "privacy-phase2b2-manual",
                "00000000-0000-0000-0000-000000000001",
                VideoSourceType.SMARTPHONE_LIVE,
                1L,
                141587L,
                now,
                now,
                BigDecimal.ONE,
                0,
                true,
                "/api/ai/events/141587/snapshot",
                4L,
                now,
                List.of()
        );
    }
}
