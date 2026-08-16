package com.visionflow.api.ai.controller;

import com.visionflow.api.ai.dto.AiPhase3DepthUpdateRequest;
import com.visionflow.api.ai.dto.AiPhase3EventCreateRequest;
import com.visionflow.api.ai.dto.AiPhase3EventResponse;
import com.visionflow.api.ai.service.AiPhase3EventService;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import org.springframework.http.HttpStatus;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@Validated
@RestController
@RequestMapping("/api/ai/phase3/events")
public class AiPhase3EventController {

    private final AiPhase3EventService eventService;

    public AiPhase3EventController(
            AiPhase3EventService eventService
    ) {
        this.eventService = eventService;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public AiPhase3EventResponse create(
            @Valid @RequestBody
            AiPhase3EventCreateRequest request
    ) {
        return eventService.create(request);
    }

    @PutMapping("/{eventKey}/depth")
    public AiPhase3EventResponse enrichDepth(
            @PathVariable
            @NotBlank
            @Size(max = 200)
            String eventKey,

            @Valid @RequestBody
            AiPhase3DepthUpdateRequest request
    ) {
        return eventService.enrichDepth(eventKey, request);
    }
}