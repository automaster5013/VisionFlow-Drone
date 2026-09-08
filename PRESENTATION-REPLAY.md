# Presentation telemetry replay

Open /presentation-replay (OPERATOR or ADMIN login required), or use the new link on /demo-mode.

1. Stop any separate server dummy feeder or phone input before starting this input.
2. Choose a presentation drone with flight clearance and no active flight session.
3. Set the simulated origin and optional repeat playback, then start.
4. Open the control/AI views in separate windows. Keep the replay tab open.
5. Pause stops both outgoing video and telemetry while retaining the session. Resume continues
   from the same video position. End completes the server flight session; reset clears only
   local playback counters and position, never stored history.

Telemetry is generated from the MP4 playhead and stored through the existing telemetry API
with telemetrySource=SIMULATOR and sourceDeviceId=presentation-simulator-001. The video uses
that same server-issued flightSessionId. The circular route has radius 35m, maximum altitude
30m, and simulated battery from 100 to 85 percent per loop. Natural video completion stores
zero altitude and speed before closing the session. Each repeat resets the simulated track
and battery. Browser background throttling can lower send frequency; playback does not queue
old frames. Closing the tab attempts to abort the owned session via sendBeacon; interrupted
network sessions may require recovery in mobile-flight.

This is a browser-controlled presentation replay, not an unattended server scheduler. Existing
model-event backend routing must target the same backend as the frontend before persisted AI
alerts can be claimed as end-to-end validated. No fabricated AI detections are injected here.

Validation: TypeScript, ESLint, production build; node --experimental-strip-types --test
01_frontend/visionflow-web/tests/presentation-telemetry.test.mjs.

Local integration verification (2026-09-08): start/pause/resume/end/reset and two-loop playback
passed against the local backend. First session stored 46 simulator telemetry rows and six
actual AI events; second session stored 131 rows (battery 85–100) across two loops. Both
sessions ended COMPLETED. The existing local frontend AI DNS target was corrected from
ai-server to visionflow-ai. The standalone server feeder was stopped to avoid competing inputs.
AWS deployment was approved and completed; end-to-end verification is recorded below.

AWS integration verified 2026-09-08: local AI event destination was switched to
http://host.docker.internal:18080/api/ai/events through a localhost-only SSH tunnel
(127.0.0.1:18080 -> AWS 127.0.0.1:8080). Existing AI authentication passed without
credential changes. AWS session f3113cd8-175e-4e38-962f-ca357cc7ffe8 stored both
SIMULATOR telemetry and actual AI events. AI still executes on the local GPU.
The PC, Docker, browser replay, and both SSH connections must remain available.
Do not use local-backend replay while the AI event destination is set to AWS;
its session identifiers belong to a different database. Tunnel restart helper is
outputs/Start-VisionFlow-Aws-Event-Tunnel.ps1 in the desktop task directory.

Final AWS verification: 107.1 seconds, 323 accepted video frames, 87 SIMULATOR telemetry rows, 11 actual AI events, session COMPLETED, final altitude and speed zero.

Browser replay source correction (2026-09-08): presentation frames explicitly pass
DUMMY_VIDEO through the authenticated proxy and AI ingestion queue. Unspecified
browser input remains SMARTPHONE_LIVE; other browser source types are rejected.
The stream and performance monitor follow the processed frame source.
Regression tests: 14 passed; frontend typecheck, lint and production build passed.
AWS verification: 82 accepted frames and 22 telemetry writes, then session ended.

The restart helpers are versioned under scripts/Start-VisionFlow-Presentation.ps1
and scripts/Start-VisionFlow-Aws-Event-Tunnel.ps1. Pass -IdentityFile and
-KnownHostsFile pointing to your existing local SSH key and trusted host file.
No keys or trusted-host files are included. These scripts target the existing
AWS deployment; the video tunnel binds AWS Docker bridge 172.17.0.1:18000,
not AWS loopback, so the frontend container can reach it. The remote SSH server
must already permit that binding. They do not change server SSH policy.

## Presentation pause ledger (2026-09-09)

POST /api/drones/{droneId}/flight-sessions/{sessionId}/pause and /resume record
server timestamps for active presentation-simulator-001 sessions only. Duplicate
pause/resume calls are idempotent; complete/abort closes an open pause. Operators
and admins use the existing authenticated mutation proxy. Failed frame delivery
does not create an intentional pause record.

Flyway V27 adds flight_session_pause; existing history is unchanged. Replay
responses include pauses. The report displays the ledger and both server quality
rule VFQ-1.1.0 and browser fallback subtract only the confirmed overlap from
telemetry gaps. Unexplained residual gaps still count; no historical pauses are
inferred. Deploy backend before frontend. Rolling back code does not require
removing the additive table.

Validation: backend full tests, pause persistence round trip with transaction
rollback, frontend pause overlap tests, TypeScript, ESLint and production build.
