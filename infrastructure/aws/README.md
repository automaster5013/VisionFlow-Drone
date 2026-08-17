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

The validated baseline is the backend image published from main commit `310b4eb92a548e8d58f9dc29f8a36544224de572`:

```text
automaster5013/visionflow-drone:backend-sha-310b4eb
sha256:20185c747bb6f45211b99e69694267ffbd8196fe8e2af51c12e13d4d979b8915
```

`deploy-backend-mysql.sh` verifies the expected digest before replacing the backend container.

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

Once the MySQL volume has been initialized, keep the database credentials aligned with the existing volume. Do not regenerate credentials during a routine redeploy.

## 2. Deploy MySQL + backend

From this directory on the EC2 host:

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

It never deletes the MySQL volume.

## 3. Point the edge Phase 3 reporter at AWS

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

## 4. Acceptance criteria

A complete Edge -> AWS Phase 3 E2E pass requires all of the following:

1. Edge AI container is healthy and CUDA GPU is visible.
2. A natural `PHASE3_PPE_TRIGGER` reaches `STATE=CONFIRMED_NO_HELMET` with `ACCEPTED=true`.
3. A corresponding `PHASE3_DEPTH_RESULT` is produced.
4. No `Phase 3 backend report failed` message is emitted for that event.
5. AWS MySQL contains the expected event key with PPE fields plus depth enrichment fields.

A validated live-camera run produced `SMARTPHONE_LIVE`, `CONFIRMED_NO_HELMET`, and a `NEAR` depth enrichment in `ai_phase3_event`. This proves the edge-to-cloud persistence path; it does not by itself prove DJI Mini 4 Pro video input.

## Safety notes

- Never run `docker compose down -v` for this deployment.
- Never delete `visionflow_mysql_data` during redeploy.
- Do not open ports 22/8080 to `0.0.0.0/0` for convenience.
- MySQL stays on the private Docker network only.
- Registry credentials should be logged out after bounded deployment work when they are no longer needed.
- Keep real secrets only in the protected EC2 `.env` file or a future secret manager; examples in Git contain placeholders only.
