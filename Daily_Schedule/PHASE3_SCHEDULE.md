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
> **현행화 기준(2026.09.09 KST):** 발표용 기능 동결, 17장 PPT 검토와 10분 노트 원고 작성, 약 3분 56초 통합 MP4 제작·검사 완료. 제출·발표 및 Gamma 노트 저장은 확인 대기입니다.
> **발표 입력:** 더미영상·가상 텔레메트리 기반 시연을 사용합니다. 실내 실기체 운용 대신 Drone-Eye 별도 DEMO를 소개하며, 스마트폰 실제 카메라·위치 재시험은 보류했습니다.
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

### P0 — 발표 산출물 준비 및 확인

- [x] 더미영상·가상 텔레메트리 기반 정상 시연 경로 확정
- [x] 09.09 세션 프레임 수락 94회·좌표 25개·AI 이벤트 4건 및 저장·재조회 확인
- [x] 서버 일시정지 기록과 품질 진단 수신 공백 구분 확인
- [x] 최종 PPT 17장 내용·레이아웃 검토
- [x] 각 페이지 시간 배분과 발표자 노트 입력 프롬프트 작성 (설명 10분)
- [x] VisionFlow + 별도 Drone-Eye 통합 MP4 제작 및 전체 디코딩·연결 지점 확인
- [x] 사용자 요청으로 현재 개발 동결, 발표자료 작업으로 전환
- [x] README·일정표 현행화
- [ ] Gamma 카드의 실제 발표자 노트 저장 확인
- [ ] 실제 발표 속도 기준 리허설과 제출·발표 완료 확인

### P1 — 발표 후 재개할 검증 (현재 동결)

- [ ] PPE S2 GPU smoke 및 추가 학습 (입력 패키지 준비와 실행 완료를 구분)
- [ ] 원거리 후보의 대표 현장 데이터 평가 및 운영 적용 판단
- [ ] 스마트폰 실제 카메라·위치 입력 재시험
- [ ] DJI Mini 4 Pro / RC-N2 / Android MSDK 실장비 E2E
- [ ] 전체 인증·배포·Rollback 회귀 재시험 (09.09 세션 검증으로 대체하지 않음)

### P2 — 발표 후 정식 품질 단계

- [ ] 재주석 34건 완전 수동 검토·보정
- [ ] 격리 HOLD 4건 추가 심사
- [ ] provenance·exact/near-duplicate Evidence를 이용한 final source-group 확정
- [ ] anti-leakage 제약을 적용한 final train/validation/test split 확정
- [ ] semantic/box Ground Truth 승인 및 전체 YOLO label QC
- [ ] 정식 PPE 4-class 학습·평가와 canonical weight 승격
- [ ] Tracking·Pose·Segmentation·고해상도/타일 추론 선택 확장

### 선행 기반 — 이전 단계 검증 기록

아래 기록은 해당 시점의 결과이며 현재 컨테이너 수·AWS 실행 상태나 09.09 현장 재시험을 뜻하지 않습니다.

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

### AI 학습·데이터 현행 상태 — 2026.09.09

기존 PPE 모델과 별도 COCO 사람 탐지 모델의 운영 구성을 유지합니다. 아래 S2 입력 준비와 기존 PPE 운영 모델은 구분합니다. 24장 후보 진단 및 원본 데이터셋 확인 결과는 [09.09 마감 기록](../docs/presentation-closeout-20260909.md)을 참조하세요.

| 구분 | 현재 상태 | 품질·승격 경계 |
|---|---|---|
| VisDrone S1 | 🟢 epoch 88 학습 완료 | 10-class canonical initializer 고정; PPE 성능을 의미하지 않음 |
| S1 weight 무결성 | 🟢 검증 완료 | `44,121,433 bytes`, SHA-256 `486f29a14b68201defb2148db923633f15b68f0304b50ff1f66b893ea4e16422` |
| PPE curated annotation pool | 🟢 준비 완료 | 전체 512건, Batch 0001 유효 focus 38건 |
| PPE disposition | 🟢 범위 승인 | 재주석 34건, 격리 HOLD 4건 |
| Provenance audit | 🟢 packet 완료 | exact/near-duplicate·MNS 정보는 anti-leakage Evidence로만 사용 |
| AI-assisted proposal | 🧪 제안 packet 완료 | 34개 이미지 처리, final GT 자동 승격 없음 |
| PPE S2 smoke 입력 | 🧪 조립 검증 완료 | 9장·87 provisional boxes, smoke-only train 7 / val 2 |
| PPE S2 1-epoch GPU smoke | ⏸️ 발표 후 재개 | 기술 파이프라인 확인용이며 정확도 평가가 아님 |
| Final source-group·split | ⏸️ HOLD | 사람 adjudication 전 자동 배정 금지 |
| Semantic/box GT | ⏸️ HOLD | reference/provisional label의 GT 자동 승격 금지 |
| PPE 본 학습·canonical 승격 | ⏸️ HOLD | 발표 후 수동 재주석·QC·split 확정 뒤 수행 |

다음은 **후속 확장 개념도**이며 현재 운영 배치가 아닙니다. S1 후보·provisional S2·Tracking/Pose/Seg를 모두 운영에 적용했다는 의미가 아닙니다.

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
| **09.07** | **기존 학습·발표 기준선 정리** | S1 canonical weight 및 PPE provisional 입력 준비 기록 정리 | GPU smoke·본 학습·정식 승격은 미완료 | 🧪 **기준선 / 잠정** |
| **09.08** | **발표 시연 기능 보완** | 더미영상·가상 텔레메트리 재생, 사람·보호구 표시 순서와 미착용 경고, 관제·보고서 흐름 보완 | 통합 결과는 09.09 세션 기록으로 확인; 실기체 시험과 구분 | 🟡 **09.09 검증으로 연결** |
| **09.09** | **검증·개발 동결·발표 산출물 완성** | 세션 기록·일시정지·저장 재조회 확인; 원거리 후보·PPE 데이터 검토 후 개발 동결; PPT 17장·10분 노트 프롬프트·통합 MP4 제작 | MP4 약 3분 56초, 전체 디코딩 검사 완료; Gamma 실제 노트 저장·제출·발표는 확인 대기 | 🟢 **자료 준비 완료** |

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
8. **Feature Freeze:** 09.07의 동결 계획 이후 발표 보완을 진행했으며, 09.09 사용자 요청 시점의 개발 상태를 동결했습니다. 추가 학습·운영 모델 교체는 후속 검증 대상으로 유지합니다.
9. **Evidence-based Status:** 실행 로그가 없는 항목은 완료로 표시하지 않고 `진행`, `실험`, `HOLD`로 구분합니다.
