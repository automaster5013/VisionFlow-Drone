VisionFlow Local Runtime v2
===========================

Normal operation
----------------
start-visionflow-local.bat

- Starts Docker Desktop if needed.
- Starts only desktop core containers:
  visionflow-mysql, visionflow-backend, visionflow-ai, visionflow-frontend.
- Does NOT auto-start mobile-https.
- Waits for Backend, AI and Frontend readiness.
- Verifies frontend auth mode=session and restart policy=unless-stopped.

Frontend UI development
-----------------------
run-frontend-dev-session.bat

- Verifies Backend and AI health first.
- Reads VISIONFLOW_AI_INTERNAL_KEY from .env.docker without printing the secret.
- Verifies the key against AI.
- Stops Docker frontend.
- Waits up to 20 seconds for port 3000 to be fully released.
- Starts Next.js dev with session/backend/AI/WebSocket variables.
- Ctrl+C restores Docker frontend automatically.

Publish current local frontend into Docker
------------------------------------------
restore-visionflow-frontend.bat

- Rebuilds frontend-web from current source.
- Recreates only frontend-web.
- Verifies session auth, AI key presence, health and restart policy.
- Does not commit or push anything.

Windows logon auto-start
------------------------
install-visionflow-autostart.bat

Optional browser opening:
install-visionflow-autostart.bat -OpenBrowser

Security
--------
- VISIONFLOW_AI_INTERNAL_KEY is never printed.
- .env.docker must remain uncommitted.
