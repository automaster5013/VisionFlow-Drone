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

> **일정 변경 확정(2026.08.31):** 최종 발표일이 2026.09.11에서 **2026.09.09로 이틀 앞당겨졌습니다.**
> **현행화 기준(2026.09.07 KST):** VisDrone S1 학습과 canonical weight 고정은 완료했습니다. PPE 4-class S2는 curated pool·provenance audit·AI-assisted proposal·smoke 입력 조립까지만 완료됐으며, 실제 GPU smoke와 본 학습은 별도 Gate입니다.
> **발표 우선 원칙:** DJI 실기체 경로가 안정적이면 사용하되, 실기체 상태가 발표를 차단하지 않도록 검증된 스마트폰·시험 영상·replay 대체 경로를 함께 고정합니다.
> **품질 경계:** provisional annotation은 최종 Ground Truth가 아닙니다. final source-group·split·semantic/box GT·canonical PPE weight 승격은 계속 `HOLD`입니다.

---

## 🏷️ 상태 표기

| 표기 | 의미 |
|:---:|---|
| ✅ **선행 완료** | 3차 착수 전에 이미 구현·검증된 기반 기능 |
| 🟡 **진행/부분 완료** | 일부 Evidence를 확보했으나 남은 검증 또는 보완이 있음 |
| 🟢 **검증 완료** | 현재 Phase 3에서 실행·검증까지 완료한 항목 |
| 🧪 **실험/잠정** | 기술 검증용 provisional 산출물이며 최종 GT·운영 모델로 승인되지 않음 |
| ⏸️ **HOLD** | 명시적 검토·승인 전에는 다음 단계로 승격하지 않음 |
| 🔵 **예정** | 3차 프로젝트 기간에 수행할 작업 |
| 🟠 **선택 확장** | 핵심 일정에 영향이 없을 때만 수행 |
| 🔴 **차단 이슈** | 핵심 E2E 진행을 막는 문제로 우선 해결 필요 |

---

## 🎯 Phase 3 성공 기준

### P0 — 09.09 발표 전 반드시 완료

- [x] VisDrone S1 10-class 학습 완료 및 canonical weight 무결성 고정
- [x] PPE Batch 0001 curated pool 512건과 유효 focus 38건의 비파괴 audit 완료
- [x] 재주석 대상 34건 AI-assisted provisional proposal packet 준비
- [x] PPE S2 1-epoch 기술 smoke 입력 9장·87 provisional boxes 조립 검증
- [ ] PPE S2 4-class 1-epoch GPU smoke를 기술 Gate로 실행하고 결과·로그·weight 보존
- [ ] smoke 통과 시에만 제한된 provisional inference Evidence 확보
- [ ] DJI 실기체 또는 검증된 스마트폰·시험 영상·replay 중 발표 정상 경로 1개 확정
- [ ] 실기체·네트워크·모델 장애 시 즉시 전환할 대체 시나리오와 복구 Runbook 고정
- [ ] Frontend·Backend·AI·MySQL의 발표용 E2E health와 Event 표시 재검증
- [x] README·일정표에 완료·잠정·HOLD 범위를 동일하게 반영
- [ ] 09.07 Feature Freeze 이후 Critical 수정 외 신규 기능 추가 중단

### P1 — P0 안정화 후 발표 전 시간이 허용될 때

- [ ] PPE S2 smoke 통과 결과를 바탕으로 제한된 provisional fine-tuning 수행
- [ ] provisional PPE checkpoint의 발표 샘플 정성 검증
- [ ] DJI Mini 4 Pro / RC-N2 / Android MSDK 실장비 camera stream 또는 telemetry 최소 Gate
- [ ] 실제/준실제 텔레메트리와 Flight Session·AI Event의 동일 세션 추적
- [ ] 개인 계정·RBAC·QR Pairing·HTTPS·CI/CD·Rollback 최종 회귀 검증

### P2 — 발표 후 정식 품질 단계

- [ ] 재주석 34건 완전 수동 검토·보정
- [ ] 격리 HOLD 4건 추가 심사
- [ ] provenance·exact/near-duplicate Evidence를 이용한 final source-group 확정
- [ ] anti-leakage 제약을 적용한 final train/validation/test split 확정
- [ ] semantic/box Ground Truth 승인 및 전체 YOLO label QC
- [ ] 정식 PPE 4-class 학습·평가와 canonical weight 승격
- [ ] Tracking·Pose·Segmentation·고해상도/타일 추론 선택 확장

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
- [x] VisDrone S1 epoch 88 early stopping 완료 및 canonical initializer 고정
- [x] PPE curated pool 512·Batch 0001 focus 38 provenance/duplicate audit 완료
- [x] 재주석 34건 AI-assisted proposal과 9장·87 box smoke 입력 조립 완료

---

## 🧠 AI 영상 추론 고도화 전략

3차 프로젝트의 AI 관제는 **Detection baseline을 먼저 검증**하고, Tracking·Pose·Segmentation은 발표 후 단계적으로 조합하는 구조로 설계합니다.

### AI 학습·데이터 현행 상태 — 2026.09.07

| 구분 | 현재 상태 | 품질·승격 경계 |
|---|---|---|
| VisDrone S1 | 🟢 epoch 88 학습 완료 | 10-class canonical initializer 고정; PPE 성능을 의미하지 않음 |
| S1 weight 무결성 | 🟢 검증 완료 | `44,121,433 bytes`, SHA-256 `486f29a14b68201defb2148db923633f15b68f0304b50ff1f66b893ea4e16422` |
| PPE curated annotation pool | 🟢 준비 완료 | 전체 512건, Batch 0001 유효 focus 38건 |
| PPE disposition | 🟢 범위 승인 | 재주석 34건, 격리 HOLD 4건 |
| Provenance audit | 🟢 packet 완료 | exact/near-duplicate·MNS 정보는 anti-leakage Evidence로만 사용 |
| AI-assisted proposal | 🧪 제안 packet 완료 | 34개 이미지 처리, final GT 자동 승격 없음 |
| PPE S2 smoke 입력 | 🧪 조립 검증 완료 | 9장·87 provisional boxes, smoke-only train 7 / val 2 |
| PPE S2 1-epoch GPU smoke | 🟡 실행 대기 | 기술 파이프라인 확인용이며 정확도 평가가 아님 |
| Final source-group·split | ⏸️ HOLD | 사람 adjudication 전 자동 배정 금지 |
| Semantic/box GT | ⏸️ HOLD | reference/provisional label의 GT 자동 승격 금지 |
| PPE 본 학습·canonical 승격 | ⏸️ HOLD | 발표 후 수동 재주석·QC·split 확정 뒤 수행 |

```text
DJI / Wireless Video
        ↓
Primary Detection
VisDrone S1 + provisional PPE S2
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

- VisDrone 기반 항공 시점 S1 Detection 학습·검증 완료
- 고해상도 `imgsz` 비교
- 타일 기반 inference(SAHI 등) 적용 가능성 검토
- 필요 시 YOLO26 P2 small-object architecture 실험
- 발표 후 PPE 수동 재주석·QC·정식 S2 학습으로 4-class 품질 보강

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
| **08.25 ~ 08.27** | **VisDrone S1 Training Readiness** | - S1 학습 계약·GPU preflight·batch 보정 기준선 확정<br>- 데이터·설정·실행 전 검증과 재개 지점 확보 | - 재현 가능한 S1 실행 기준선<br>- 실행 전에는 weight 완료로 표기하지 않음 | 🟢 **완료** |
| **08.28 ~ 08.31** | **AWS Hybrid 최소 E2E + S1 기준선 진행** | - AWS EC2 Frontend·Backend·MySQL 배포<br>- Local AI Event의 AWS Backend 전달<br>- MySQL 1행·Frontend 표시 및 presentation readiness 확인<br>- VisDrone S1 학습·평가 진행과 안전한 재개 | - HTTP 201, DB Evidence, Frontend 표시 PASS<br>- AWS 기준선 보존 및 과금 제어 | 🟢 **검증 완료** |
| **09.01 ~ 09.03** | **VisDrone S1 완료·Checkpoint 고정 / DJI Gate 보존** | - VisDrone 항공 시점 10-class Detection S1 학습 완료<br>- canonical best weight 이름·크기·SHA-256 고정<br>- DJI 실장비 Gate는 완료 증거 없이 미검증 상태 유지 | - `yolo26m-visdrone-s1-best.pt` 확보<br>- epoch 88 early stopping 및 무결성 확인<br>- DJI 실기체 결과 과장 없음 | 🟢 **S1 완료** |
| **09.04 ~ 09.06** | **PPE Batch 0001 Data Fast-track** | - curated annotation pool 512건 구축<br>- 64건 계약 캘리브레이션·disposition 승인<br>- 유효 focus 38건을 재주석 34·격리 HOLD 4로 확정<br>- provenance·exact/near-duplicate·MNS audit<br>- AI-assisted proposal v1r1 생성과 smoke 입력 9장·87 boxes 조립 | - 원본 curated tree 변경 0<br>- proposal-only·assembly-only PASS<br>- final group·split·GT·학습 자동 승격 0 | 🟢 **잠정 입력 준비 완료** |
| **09.07** | **Feature Freeze / PPE S2 Smoke Gate** | - Critical 수정 외 신규 기능 추가 중단<br>- PPE S2 4-class 1-epoch GPU smoke 별도 실행·기술 검증<br>- 성공 시 provisional inference 샘플·로그·weight 보존<br>- 실패 시 반복 튜닝보다 S1·기존 검증 경로 기반 발표 fallback 고정 | - 실제 실행 결과가 있을 때만 smoke PASS 표기<br>- final GT·canonical PPE 승격 없음<br>- 정상/대체 시나리오 결정 | 🟡 **진행/실행 대기** |
| **09.08** | **최종 리허설 / 문서·산출물 동결** | - Frontend·Backend·AI·MySQL 정상 시나리오 반복 검증<br>- 실기체 실패 시 스마트폰·시험 영상·replay 대체 시나리오 리허설<br>- README·일정표·Architecture·발표 자료 현행화<br>- 로그·DB·화면·weight provenance Evidence 선별 | - 리허설 PASS<br>- 발표 PC·케이블·배터리·네트워크·복구 Runbook 점검<br>- 완료·잠정·HOLD 표기 일치 | 🔵 **예정** |
| **09.09** | **3차 프로젝트 최종 시연·발표** | - 검증된 정상 또는 대체 입력 기반 관제 시연<br>- Local Edge AI + AWS Hybrid + CI/CD·Rollback 설명<br>- VisDrone S1 완료와 PPE S2 provisional fast-track을 구분해 설명<br>- DJI·final GT·정식 PPE 학습의 미완료 범위를 투명하게 제시 | - 최종 발표 및 산출물 제출 | 🏆 **최종 발표** |

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

> 위 결과는 Hybrid 서비스·Event 전달 경로의 Evidence이며 DJI 실기체 영상이나 DJI stream 기반 GPU 실시간 추론 완료를 의미하지 않습니다.

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

1. **Presentation Path First:** 검증된 입력 → Local Edge Detection → Event/Telemetry → Dashboard 경로 하나를 먼저 고정합니다.
2. **Hardware Is Not a Single Point of Failure:** DJI 실기체가 불안정하면 스마트폰·시험 영상·replay 대체 경로로 즉시 전환합니다.
3. **S1/S2 단계 분리:** 완료된 VisDrone S1을 재실행하지 않고 다음 AI Gate는 PPE S2 4-class로 한정합니다.
4. **Provisional Is Not Ground Truth:** AI proposal·reference label·smoke 입력은 최종 GT로 자동 승격하지 않습니다.
5. **Anti-leakage Before Split:** exact/near-duplicate와 must-not-split Evidence를 검토한 뒤에만 final split을 확정합니다.
6. **Canonical Promotion Gate:** 정식 PPE weight는 수동 재주석·QC·source-group·split·평가 완료 뒤에만 승격합니다.
7. **AWS 기준선 동결:** 검증된 Hybrid 배치에는 발표를 위협하는 신규 기능을 추가하지 않습니다.
8. **Feature Freeze:** 09.07부터 Critical 수정과 발표 Evidence 보완 외 변경을 중단합니다.
9. **Evidence-based Status:** 실행 로그가 없는 항목은 완료로 표시하지 않고 `진행`, `실험`, `HOLD`로 구분합니다.
