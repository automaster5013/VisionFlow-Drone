# 📅 [Phase 3] VisionFlow-Drone 상세 작업 일정표

## 프로젝트 기본 정보

| 항목 | 내용 |
|---|---|
| 팀명 | **PyvaOps** |
| 팀원 | **이명휘** |
| 프로젝트명 | **VisionFlow-Drone** |
| 주제 | **무선 영상·텔레메트리 기반 지능형 드론 관제 및 Vision AI 표준 파이프라인** |
| 3차 프로젝트 기간 | **2026.08.19 ~ 2026.09.09** |
| GitHub | `automaster5013/VisionFlow-Drone` |

> **일정 변경 확정(2026.08.31):** 최종 발표일이 2026.09.11에서 **2026.09.09로 이틀 앞당겨졌습니다.**<br>
> **운영 원칙:** 남은 기간에는 `DJI Mini 4 Pro → Local Edge AI → 텔레메트리/이벤트 → 관제 대시보드`의 정상 시나리오와 대체 시나리오를 우선 고정합니다. AWS Spike는 GO로 종료했으며, 검증된 Hybrid 기준선은 변경하지 않고 발표 Evidence가 필요할 때만 재가동합니다.

---

## 🏷️ 상태 표기

| 표기 | 의미 |
|:---:|---|
| ✅ **선행 완료** | 3차 착수 전에 이미 구현·검증된 기반 기능 |
| 🟡 **진행/부분 완료** | 일부 Evidence를 확보했으나 남은 검증 또는 보완이 있음 |
| 🟢 **검증 완료** | 현재 Phase 3에서 실행·검증까지 완료한 항목 |
| 🔵 **예정** | 3차 프로젝트 기간에 수행할 작업 |
| 🟠 **선택 확장** | 핵심 일정에 영향이 없을 때만 수행 |
| 🔴 **차단 이슈** | 핵심 E2E 진행을 막는 문제로 우선 해결 필요 |

---

## 🎯 Phase 3 성공 기준

### P0 — 09.09 발표 전 반드시 완료

- [ ] DJI Mini 4 Pro / RC-N2 / Android DJI MSDK Bridge 실장비 연결과 camera availability/encoded stream 최소 검증
- [ ] 실제 장치 경로가 가능한 경우 MSDK stream 또는 telemetry 중 최소 한 경로를 Local Edge 서비스와 연결
- [ ] 발표용 정상 시나리오 1개를 고정하고 Frontend·Backend·AI·MySQL 상태를 한 번에 검증
- [ ] 실기체·네트워크 장애 시 즉시 전환할 스마트폰/더미 영상 기반 대체 시나리오 고정
- [ ] 발표 직전 무변경 readiness, 복구 Runbook, 시연 캡처·로그·DB Evidence 확정
- [ ] 09.07 Feature Freeze 이후 신규 기능 추가 없이 Critical issue 0 유지

### P1 — P0 안정화 후 남은 기간에 수행

- [ ] RTX Edge GPU에서 `yolo26m.pt` Detection 또는 검증된 기존 모델의 발표 기준선 확보
- [ ] `best.pt` PPE/안전 탐지 모델의 데이터·라벨·학습 설정·검증 지표 재점검
- [ ] 실제/준실제 텔레메트리와 Flight Session·AI Event의 동일 세션 추적
- [ ] 개인 계정·RBAC·QR Pairing·HTTPS·CI/CD·Rollback 핵심 회귀 검증

### P2 — 시간 허용 시 또는 발표 후 확장

- [ ] Pose Estimation·Instance Segmentation의 선택적/단계적 추론 통합
- [ ] BoT-SORT 또는 ByteTrack 기반 객체 ID·궤적 유지
- [ ] VisDrone 재학습·고해상도/타일 추론 기반 원거리·소형 객체 개선
- [ ] Pose 위험 행동 규칙과 Segmentation 위험영역 판정 실험

### 선행 기반 — 이미 검증

- [x] 스마트폰 실제 GPS·방향 센서 + 후면 카메라 + YOLO 통합 E2E
- [x] 개인 계정 로그인 + DB Role 기반 VIEWER / OPERATOR / ADMIN RBAC + HttpOnly 브라우저 세션
- [x] SecureRandom 초기 비밀번호 자동 생성 + 최초 비밀번호 변경 강제 + 초기 credential 자동 폐기
- [x] 보안 QR Pairing
- [x] Caddy 기반 모바일 HTTPS
- [x] Phase 3 `DJI_LIVE` Event ingest/depth enrichment + observability runtime 검증
- [x] DJI MSDK Android Bridge camera listener 컴파일 + Debug APK 빌드
- [x] Docker Hub immutable SHA image publish
- [x] GitHub Actions CI/CD + Windows self-hosted runner
- [x] Health Check 및 Automatic Rollback
- [x] 발표용 Docker 기준선 5 images / 5 healthy containers + Build Cache 0B 정리
- [x] Local AI + AWS Frontend/Backend/MySQL Hybrid 배포 및 SSH 터널 접근 검증
- [x] Local AI → AWS Phase 3 Event HTTP 201, MySQL 정확히 1행, AWS Frontend 표시 검증
- [x] AWS 발표 readiness PASS 후 EC2 정상 중지, Elastic IP·EBS 보존

---

## 🧠 AI 영상 추론 고도화 전략

3차 프로젝트의 AI 관제는 단일 모델에 모든 기능을 억지로 결합하기보다, **Detection을 중심으로 Tracking·Pose·Segmentation을 단계적으로 조합하는 Multi-Task Inference Pipeline**으로 설계합니다.

```text
DJI / Wireless Video
        ↓
Primary Detection
yolo26m.pt + custom best.pt
        ↓
Tracking
BoT-SORT / ByteTrack
        ↓
┌──────────────────────┐
│ Person / Risk ROI    │
├──────────┬───────────┤
│ Pose     │ Segment   │
│ yolo26m- │ yolo26m-  │
│ pose.pt  │ seg.pt    │
└──────────┴───────────┘
        ↓
AI Event / Snapshot / Track / Risk Rule
        ↓
VisionFlow Dashboard / MySQL
```

### 원거리·소형 객체 대응

- VisDrone 기반 항공 시점 Detection 학습·검증
- 고해상도 `imgsz` 비교
- 타일 기반 inference(SAHI 등) 적용 가능성 검토
- 필요 시 YOLO26 P2 small-object architecture 실험
- `best.pt`의 드론 시점·원거리 샘플 보강 및 재학습

### 성능·품질 Gate

- Detection: Precision / Recall / mAP50 / mAP50-95
- Small Object: 원거리 샘플 Recall 및 미탐률
- Tracking: ID 유지율 / ID switch 관찰
- Runtime: FPS / p50·p95 inference latency / queue drop / VRAM
- Pose/Seg: 실시간 적용 범위를 GPU 성능에 맞춰 선택적으로 조절

---

## 🗓️ 상세 실행 일정

| 기간 | Milestone | 주요 작업 | 완료 기준 / Evidence | 상태 |
|---|---|---|---|:---:|
| **08.13 ~ 08.18** | **Phase 3 사전 기술 검증 / 보안·배포·DJI Bridge Readiness** | - AWS EC2·Security Group·SSH·Docker 및 Edge → AWS JSON Event 검증<br>- Phase 3 Backend `DJI_LIVE` Event ingest/depth observability Docker runtime 검증<br>- 개인 계정 로그인·DB Role RBAC·자동 초기 비밀번호·최초 변경 강제 적용 및 실제 브라우저 검증<br>- DJI MSDK `DjiSdkBootstrap.kt` camera availability/encoded stream listener 구현 및 `assembleDebug` PASS<br>- Docker 이미지 5개/healthy 컨테이너 5개로 발표 기준선 정리, Build Cache 0B<br>- AWS EC2 `VisionFlow-Drone` 중지 및 Elastic IP 유지로 비용 제어<br>- DJI 기체·RC-N2·스마트폰·배터리·데이터 케이블 준비 | - Backend ingest/depth observability 로그 PASS<br>- VIEWER/OPERATOR/ADMIN 계정·최초 비밀번호 변경 PASS<br>- `app-debug.apk` 생성<br>- Docker 5-service healthy<br>- AWS 선택 확장 재개 가능 상태 보존 | ✅ **선행 완료** |
| **08.19 ~ 08.20** | **Phase 3 Kickoff / DJI MSDK 실장비 Gate** | - 2차 기준선과 P0/P1 범위 재확인<br>- Debug APK와 MSDK camera listener 빌드 기준선 유지<br>- 실장비 Gate는 안전한 실기 여건 확보 후 수행하도록 보류 | - 소스·APK readiness 유지<br>- 미검증 실장비 결과를 완료로 표기하지 않음 | 🔴 **실기 여건 보류** |
| **08.21 ~ 08.22** | **SQLD 일정 보호 / 저개입 자동 검증** | - SQLD 시험 일정을 우선 보호<br>- 프로젝트 변경을 최소화하고 자동 검증·기록 중심으로 운영 | - 시험 일정 침해 없음<br>- 프로젝트 재개 기준선 유지 | ✅ **완료** |
| **08.23 ~ 08.24** | **Core UI·인증·HTTPS 회귀 / MSDK PoC 보류** | - Frontend 운영 UI·RBAC·세션·QR Pairing·HTTPS 회귀 검증<br>- MSDK 실장비 입력은 환경 확보 전까지 변경 없이 보존 | - 주요 Frontend/API 회귀 PASS<br>- MSDK 미검증 범위 명시 | 🟡 **부분 완료** |
| **08.25 ~ 08.27** | **AI Training Readiness·소형 객체 대응 기반** | - VisDrone S1 학습 계약·GPU preflight·batch 보정 기준선 정리<br>- Controlled live/replay 및 observability 계약 강화<br>- 최종 weight 생성 없이 재현 가능한 재개 지점 보존 | - S1 CPU/GPU readiness 확보<br>- 학습·실추론 완료로 과장하지 않음 | 🟡 **부분 완료** |
| **08.28 ~ 08.31** | **S1 Fallback 정리 + AWS Hybrid 최소 E2E** | - S1 replay summary·historical evidence 복구<br>- AWS EC2에 Frontend·Backend·MySQL 배포<br>- Local AI Event 대상 두 경로를 AWS SSH 터널로 전환<br>- 통제 Phase 3 Event 1건을 HTTP 201로 저장하고 MySQL 1행·Frontend 표시 확인<br>- presentation readiness PASS 후 EC2 정상 중지, Elastic IP·EBS 유지 | - Local AI → AWS Backend/MySQL → Frontend Evidence PASS<br>- AWS 기준선 보존 및 과금 제어<br>- DJI·GPU 실추론은 미수행으로 구분 | 🟢 **Hybrid 검증 완료** |
| **09.01 ~ 09.03** | **DJI / Local Edge AI Core Recovery Sprint** | - ADB·MSDK Product·camera availability·encoded stream 최소 Gate 재개<br>- 실장비가 차단되면 스마트폰/더미 영상 대체 입력을 즉시 고정<br>- 발표에 필요한 Detection 경로와 Event/Telemetry 연결만 우선 안정화<br>- AWS는 새 기능 없이 보존된 Evidence 확인 시에만 재가동 | - 실장비 또는 대체 입력 중 정상 경로 1개 확정<br>- 차단 사유와 대체 경로 문서화 | 🔵 **예정** |
| **09.04 ~ 09.06** | **통합 QA / 보안 / 배포 회귀** | - Frontend·Backend·AI·MySQL 통합 health와 주요 API 검증<br>- 개인 계정·Role·세션·QR Pairing·HTTPS 회귀<br>- Docker Hub Release·Private CD·Rollback 핵심 경로 확인<br>- 발표 데이터·로그·DB Evidence 선별 | - 정상 시나리오 E2E PASS<br>- 주요 회귀 PASS 및 Critical issue 정리 | 🔵 **예정** |
| **09.07** | **Feature Freeze / 정상·대체 시나리오 고정** | - 신규 기능 추가 중단<br>- 정상 시연 순서와 실기체·네트워크 장애 시 대체 경로 고정<br>- 복구 Runbook과 발표 PC·케이블·배터리 점검 | - Critical issue 0 또는 명시적 우회 절차<br>- 정상/대체 시나리오 문서 고정 | 🔵 **예정** |
| **09.08** | **최종 리허설 / 문서·산출물 고정** | - 전체 시나리오 반복 리허설<br>- README·Architecture·일정표 최종 현행화<br>- Demo 캡처·영상·CI/CD·Hybrid Evidence 선별<br>- 구현·선택 확장·미완료 항목 명확히 구분 | - 최종 리허설 PASS<br>- 발표 자료와 제출 산출물 고정 | 🔵 **예정** |
| **09.09** | **3차 프로젝트 최종 시연·발표** | - 검증된 정상 또는 대체 입력 기반 관제 시연<br>- Local Edge AI + AWS Hybrid 설계와 CI/CD·Rollback 결과 설명<br>- DJI·GPU 등 미완료 범위와 후속 확장 방향을 투명하게 제시 | - 최종 발표 및 산출물 제출 | 🏆 **최종 발표** |

---

## ☁️ AWS Spike — GO 판정 및 기준선 고정

AWS는 Local Edge AI를 대체하지 않는 **Frontend·Backend·MySQL 확장 배치**로 검증했습니다. 2026.08.31 최소 Hybrid E2E와 발표 readiness를 통과했으므로 Spike는 GO로 종료하며, 남은 일정에는 새 AWS 기능을 추가하지 않습니다.

### 검증 결과

- [x] AWS EC2 Frontend·Backend·MySQL 배포 및 health 확인
- [x] Frontend → Backend → MySQL `/api/drones` HTTP 200·JSON 확인
- [x] Local AI → AWS Phase 3 Event HTTP 201 확인
- [x] AWS MySQL 발표 증거 Event 정확히 1행 및 AWS Frontend 표시 확인
- [x] Frontend·Backend SSH 터널 접근과 비공개 MySQL 네트워크 경계 확인
- [x] 발표 readiness PASS 후 EC2 정상 중지, Elastic IP·EBS 보존

> 위 결과는 Hybrid 서비스·Event 전달 경로의 Evidence이며 DJI 실기체 영상이나 GPU 실제 추론 완료를 의미하지 않습니다.

### 최초 GO 조건

- Edge PC → AWS EC2 API 통신 성공
- VisionFlow 형태 JSON Event 전달 및 서버 로그 확인
- 4~6시간 이내에 네트워크·보안·Docker 운용이 감당 가능한 수준으로 판단
- DJI / Edge AI P0 일정에 영향이 없음

### 중단 조건

- IAM / Security Group / 네트워크 문제만으로 과도한 시간 소비
- AWS 구현이 DJI 실기체·Edge AI 일정에 영향을 주기 시작함
- GPU quota·비용·운영 복잡도가 프로젝트 가치보다 커짐
- 안정적 시연 경로를 위협함

> 남은 기간에는 AWS 기준선을 동결합니다. 재가동은 발표 Evidence 확인처럼 목적과 종료 시점이 명확한 경우에만 수행합니다.

---

## 🔒 일정 관리 원칙

1. **P0 Core 우선:** DJI 또는 검증된 대체 입력 → Local Edge Detection → Telemetry/Event → Dashboard의 발표 가능 경로를 먼저 완성합니다.
2. **AWS 기준선 동결:** 검증된 Hybrid 배치에는 신규 기능을 추가하지 않고 Local Edge/DJI Core에 집중합니다.
3. **Feature Freeze:** 09.07부터 신규 기능을 추가하지 않습니다.
4. **Recovery First:** 실기체·네트워크 장애를 고려해 항상 대체 시연 경로를 유지합니다.
5. **매일 현행화:** 실제 진행 결과에 따라 본 일정표의 상태와 Evidence를 갱신합니다.
