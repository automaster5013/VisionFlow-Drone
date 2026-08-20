# VisionFlow Phase 3 AWS Runtime

This directory contains the reproducible cloud-control-plane deployment used for Phase 3.

## Architecture

The Phase 3 deployment keeps GPU inference at the edge and persists operational events in AWS:

```text
Camera / DJI input
  -> Edge AI (GPU: tracking + PPE + Pose + async Depth)
  -> Phase 3 reporter (HTTP)
  -> AWS EC2 Spring Boot backend
  -> AWS MySQL ai_phase3_event
```

The AWS host intentionally runs only MySQL and the backend in this deployment. The AI server remains on the GPU edge host. The frontend can be deployed separately later.

## Validated release artifact

The current validated backend release is:

```text
automaster5013/visionflow-drone:backend-sha-52e847e
sha256:94d53419ae1a93809c7692350db792b208ee488813f62fd64b17dc4b586a06b3
```

On 2026-08-20 the AWS Day 4 drill verified the release through candidate smoke health, Phase 3 event/depth log markers, immutable promotion, manual rollback, database persistence after rollback, and final re-promotion. The final runtime used the immutable image reference above and reported Spring Boot/MySQL health `UP`.

`deploy-backend-mysql.sh` verifies the expected digest during bootstrap deployment. `promote-backend.sh` is the routine release path: it verifies both the immutable tag and registry digest before promotion and preserves the previous backend as a stopped rollback container.

## EC2 prerequisites

- Ubuntu/x86_64 host with Docker installed.
- At least 2 GiB RAM is recommended for the backend + MySQL pair; swap is useful on small instances.
- Security Group inbound TCP `22` and `8080` should be restricted to the operator/edge public IP CIDR.
- Do not expose MySQL `3306` publicly.
- Authenticate Docker to the private registry before the first pull when required.
- Use a least-privilege AWS identity for normal operation.

## 1. Prepare the cloud environment file

Copy the example outside the Git working tree on the EC2 host:

```bash
mkdir -p /home/ubuntu/visionflow-cloud
cp cloud.env.example /home/ubuntu/visionflow-cloud/.env
chmod 600 /home/ubuntu/visionflow-cloud/.env
```

Replace every `replace-with-...` value with a strong secret. Never commit the real `.env`.

The two release fields are deployment metadata and must move together:

```text
VISIONFLOW_BACKEND_IMAGE=automaster5013/visionflow-drone:backend-sha-52e847e
VISIONFLOW_BACKEND_EXPECTED_DIGEST=sha256:94d53419ae1a93809c7692350db792b208ee488813f62fd64b17dc4b586a06b3
```

Once the MySQL volume has been initialized, keep the database credentials aligned with the existing volume. Do not regenerate credentials during a routine redeploy.

## 2. Bootstrap MySQL + backend

Use `deploy-backend-mysql.sh` for initial/bootstrap deployment or deliberate runtime reconstruction:

```bash
chmod +x deploy-backend-mysql.sh
./deploy-backend-mysql.sh /home/ubuntu/visionflow-cloud/.env
```

The script is intentionally bounded:

- creates/reuses Docker network `visionflow-cloud`;
- creates/reuses volume `visionflow_mysql_data`;
- starts `mysql:8.4` without publishing port 3306;
- pulls and digest-verifies the immutable backend release image;
- recreates only `visionflow-backend-cloud`;
- exposes backend port 8080;
- waits for Spring Boot health;
- verifies Flyway V24 and the `ai_phase3_event` table.

It never deletes the MySQL volume. Do not use this bootstrap script as the routine promotion mechanism because it removes the current backend container before the replacement has passed health validation.

## 3. Routine immutable backend promotion

`promote-backend.sh` captures the promotion/rollback contract used by the AWS Day 4 drill. It expects the current runtime shape to match the validated cloud backend: network `visionflow-cloud`, restart policy `unless-stopped`, host port `8080`, and no backend mounts. It fails closed if unsupported runtime state would otherwise be lost during recreation; existing Docker memory/memory-swap limits are preserved for the smoke and promoted containers.

Prepare a candidate smoke container on loopback port `18080`:

```bash
chmod +x promote-backend.sh
sudo ./promote-backend.sh prepare-smoke
```

Generate one bounded Phase 3 event plus depth-enrichment request against `127.0.0.1:18080`. Use a disposable/approved AWS flight session and verify that the smoke logs contain both markers:

```text
VISIONFLOW_PHASE3_EVENT_INGEST
VISIONFLOW_PHASE3_DEPTH_ENRICH
```

Then run the gate and promotion:

```bash
sudo ./promote-backend.sh preflight
sudo ./promote-backend.sh promote
```

Promotion does the following:

1. verifies `backend-sha-<commit>` naming plus the expected registry digest;
2. requires current and smoke health `UP`;
3. requires smoke image identity to match the candidate image;
4. requires both Phase 3 structured-log markers;
5. stores sanitized runtime metadata, protected logs, and release metadata under `/home/ubuntu/visionflow-cloud/rollback/<UTC timestamp>`;
6. preserves the previous backend as `visionflow-backend-cloud-rollback-<UTC timestamp>` with restart policy `no`;
7. starts the immutable candidate on port 8080 with the current runtime environment;
8. automatically restores the previous backend if candidate start, health, or image-identity validation fails.

The temporary environment copy used during recreation is mode `600`, lives under `/tmp`, and is deleted on exit. Rollback runtime snapshots intentionally omit `Config.Env`, so application secrets are not persisted in runtime metadata; rollback metadata and captured logs are stored with restrictive permissions.

### Manual rollback

Use the exact backup-container name printed by a successful promotion:

```bash
sudo ./promote-backend.sh rollback visionflow-backend-cloud-rollback-YYYYMMDDTHHMMSSZ
```

The manual rollback command restores the selected backup as `visionflow-backend-cloud`, reapplies the current restart policy, starts it, and requires health `UP` before reporting `AWS_BACKEND_MANUAL_ROLLBACK=PASS`.

After a rollback drill, prepare a fresh smoke container and re-promote the intended immutable release so the final runtime provenance remains the `backend-sha-<commit>` tag.

## 4. Point the edge Phase 3 reporter at AWS

Use `edge-phase3-reporter.override.example.yaml` as the final Compose override on the GPU edge host. Supply the AWS backend base URL and an ACTIVE flight-session UUID:

```text
VISIONFLOW_AWS_BACKEND_URL=http://<restricted-ec2-address>:8080
VISIONFLOW_AWS_SESSION_ID=<active-flight-session-uuid>
```

The resulting AI environment must contain:

```text
AI_PHASE3_REPORT_EVENTS=true
AI_SESSION_ID=<AWS active session UUID>
AI_BACKEND_PHASE3_EVENT_URL=http://<aws-backend>:8080/api/ai/phase3/events
```

## 5. Acceptance criteria

A complete Edge -> AWS Phase 3 E2E pass requires all of the following:

1. Edge AI container is healthy and CUDA GPU is visible.
2. A natural `PHASE3_PPE_TRIGGER` reaches `STATE=CONFIRMED_NO_HELMET` with `ACCEPTED=true`.
3. A corresponding `PHASE3_DEPTH_RESULT` is produced.
4. No `Phase 3 backend report failed` message is emitted for that event.
5. AWS MySQL contains the expected event key with PPE fields plus depth enrichment fields.

A validated live-camera run produced `SMARTPHONE_LIVE`, `CONFIRMED_NO_HELMET`, and a `NEAR` depth enrichment in `ai_phase3_event`. This proves the edge-to-cloud persistence path; it does not by itself prove DJI Mini 4 Pro video input.

## Safety notes

- Never run `docker compose down -v` for this deployment.
- Never delete `visionflow_mysql_data` during redeploy or rollback.
- Do not open ports 22/8080 to `0.0.0.0/0` for convenience.
- Candidate smoke binds to `127.0.0.1:18080`; do not expose it publicly.
- MySQL stays on the private Docker network only.
- Preserve rollback containers/artifacts until post-promotion persistence is verified.
- Registry credentials should be logged out after bounded deployment work when they are no longer needed.
- Keep real secrets only in the protected EC2 `.env` file or a future secret manager; examples in Git contain placeholders only.
