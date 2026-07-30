package com.visionflow.api.ai.controller;

import com.visionflow.api.ai.dto.AiInferenceEventCreateRequest;
import com.visionflow.api.ai.dto.AiInferenceEventResponse;
import com.visionflow.api.ai.service.AiInferenceEventService;
import jakarta.validation.Valid;
import org.springframework.core.io.Resource;
import org.springframework.http.CacheControl;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpHeaders;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

import java.util.List;

@RestController
@RequestMapping("/api/ai/events")
public class AiInferenceEventController {

    private final AiInferenceEventService eventService;

    public AiInferenceEventController(
            AiInferenceEventService eventService
    ) {
        this.eventService = eventService;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public AiInferenceEventResponse create(
            @Valid @RequestBody
            AiInferenceEventCreateRequest request
    ) {
        return eventService.create(request);
    }

    @GetMapping
    public List<AiInferenceEventResponse> findRecent(
            @RequestParam(required = false)
            Long droneId,

            @RequestParam(defaultValue = "100")
            int limit
    ) {
        return eventService.findRecent(droneId, limit);
    }

    @PutMapping(
            path = "/{eventId}/snapshot",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE
    )
    public AiInferenceEventResponse uploadSnapshot(
            @PathVariable Long eventId,
            @RequestPart("file") MultipartFile file
    ) {
        return eventService.attachSnapshot(eventId, file);
    }

    @GetMapping("/{eventId}/snapshot")
    public ResponseEntity<Resource> findSnapshot(
            @PathVariable Long eventId
    ) {
        var snapshot = eventService.findSnapshot(eventId);

        return ResponseEntity.ok()
                .cacheControl(CacheControl.noCache())
                .header(
                        HttpHeaders.CONTENT_DISPOSITION,
                        "inline; filename=\"" + snapshot.fileName() + "\""
                )
                .contentType(MediaType.parseMediaType(snapshot.contentType()))
                .contentLength(snapshot.sizeBytes())
                .body(snapshot.resource());
    }
}
