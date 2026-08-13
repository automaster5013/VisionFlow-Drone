# 📅 [Phase 3] VisionFlow-Drone 상세 작업 일정표

## 프로젝트 기본 정보

| 항목 | 내용 |
|---|---|
| 팀명 | **PyvaOps** |
| 팀원 | **이명휘** |
| 프로젝트명 | **VisionFlow-Drone** |
| 주제 | **무선 영상·텔레메트리 기반 지능형 드론 관제 및 Vision AI 표준 파이프라인** |
| 3차 프로젝트 기간 | **2026.08.18 ~ 2026.09.11** |
| GitHub | `automaster5013/VisionFlow-Drone` |

> **일정 운영 원칙:** 3차 프로젝트의 핵심은 `DJI Mini 4 Pro → Edge GPU Vision AI → 텔레메트리/이벤트 → 관제 대시보드`의 실제 End-to-End 검증입니다.
> AWS는 핵심 기능을 대체하지 않으며, **4~6시간 Time-boxed Go / No-Go Spike**를 통과한 경우에만 Edge–Cloud 확장 항목으로 진행합니다.

---

## 🏷️ 상태 표기

| 표기 | 의미 |
|:---:|---|
| ✅ **선행 완료** | 3차 착수 전에 이미 구현·검증된 기반 기능 |
| 🟡 **사전 검증** | 공식 착수 전 기술 타당성·환경 검증 중 |
| 🔵 **예정** | 3차 프로젝트 기간에 수행할 작업 |
| 🟠 **선택 확장** | 핵심 일정에 영향이 없을 때만 수행 |
| 🔴 **차단 이슈** | 핵심 E2E 진행을 막는 문제로 우선 해결 필요 |

---

## 🎯 Phase 3 성공 기준

### P0 — 반드시 완료

- [ ] DJI Mini 4 Pro / RC-N2 / DJI Fly 기반 실제 영상 입력 경로 검증
- [ ] 무선 영상 입력을 Edge AI 서버가 수신할 수 있는 어댑터 또는 중계 경로 확정
- [ ] RTX Edge GPU에서 **YOLO26m 기반 Detection을 기본 추론 모델**로 전환하고 성능 기준선 확보
- [ ] `best.pt` PPE/안전 탐지 모델의 데이터·라벨·학습 설정·검증 지표를 재점검하고 퀄리티 고도화
- [ ] `yolo26m-pose.pt` 기반 Pose Estimation과 `yolo26m-seg.pt` 기반 Instance Segmentation을 선택적/단계적 추론 파이프라인으로 통합
- [ ] Detection/Pose/Segmentation 결과에 BoT-SORT 또는 ByteTrack 기반 Tracking을 결합해 객체 ID·궤적 유지
- [ ] VisDrone 기반 항공 시점 학습·벤치마크와 고해상도/타일 추론 실험으로 원거리·소형 객체 탐지 보완
- [ ] 실제/준실제 텔레메트리와 비행 세션을 동일 세션으로 연결
- [ ] AI 이벤트·텔레메트리·비행 이력을 MySQL에 저장
- [ ] Next.js 관제 대시보드에서 실시간 상태·AI 결과·경로 확인
- [ ] 현장 시연용 End-to-End 시나리오와 복구 절차 검증

### P1 — 핵심 완료 후 확장

- [ ] AWS Edge–Cloud Hybrid Go / No-Go 결과 반영
- [ ] GO인 경우 AI Event / Telemetry의 AWS 전달 및 로그·저장 최소 검증
- [ ] Pose 기반 쓰러짐·위험 행동 규칙 및 이벤트 정책 실험
- [ ] Segmentation 결과를 위험영역·작업구역 판정에 활용하는 선택 기능 검토

### 선행 기반 — 이미 검증

- [x] 스마트폰 실제 GPS·방향 센서 + 후면 카메라 + YOLO 통합 E2E
- [x] VIEWER / OPERATOR / ADMIN RBAC 및 브라우저 세션
- [x] 보안 QR Pairing
- [x] Caddy 기반 모바일 HTTPS
- [x] Docker Hub immutable SHA image publish
- [x] GitHub Actions CI/CD + Windows self-hosted runner
- [x] Health Check 및 Automatic Rollback

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
| **08.13 ~ 08.17** | **Phase 3 사전 기술 검증 + AI 추론 고도화 선행 착수** | - AWS EC2·Security Group·SSH·Docker 기초 실습<br>- Edge PC → AWS EC2 Docker API JSON POST 검증<br>- AWS Hybrid는 4~6시간 Time-box로 GO / NO-GO 판단<br>- `yolo26n.pt` 현행 기준선과 `yolo26m.pt` FPS·지연·탐지 품질 비교<br>- `yolo26m-pose.pt` / `yolo26m-seg.pt` 단독 추론 Smoke Test<br>- `best.pt` 데이터·라벨·오탐/미탐·mAP/Precision/Recall 품질 점검<br>- VisDrone 데이터셋/벤치마크 준비 및 원거리·소형 객체 샘플 평가<br>- DJI 기체·RC-N2·스마트폰·배터리·케이블 준비 | - Edge → AWS 테스트 Event HTTP 200<br>- AWS Docker 로그에서 Event 확인<br>- YOLO26m 전환 가능성 판단<br>- Pose/Seg 모델 실행 가능 확인<br>- `best.pt` 개선 항목과 VisDrone 적용 계획 문서화<br>- 핵심 일정 침해 없이 AWS GO / NO-GO 판단 | 🟡 **사전 검증** |
| **08.18** | **Phase 3 Kickoff / Baseline 고정** | - 2차 구현 기준선 점검<br>- 현재 Docker·CI/CD·HTTPS·RBAC 상태 확인<br>- 3차 P0/P1 범위와 장애 대응 기준 확정<br>- 실기체 안전 점검 체크 | - Baseline 재현 가능<br>- 3차 작업 범위·중단 기준 문서화 | 🔵 **예정** |
| **08.19 ~ 08.20** | **DJI 실기체 연결 및 영상 인터페이스 검증** | - Mini 4 Pro ↔ RC-N2 ↔ DJI Fly 연결<br>- 프로펠러 비가동 상태 Live View 확인<br>- DJI Fly의 Live Streaming/지원 출력 메뉴 실제 확인<br>- RTMP 등 사용 가능한 영상 송출 인터페이스 결정 | - 실기체 Live View 확인<br>- 사용할 무선 영상 경로 1개 확정<br>- 지원 불가 항목은 대체 입력 방식 결정 | 🔵 **예정** |
| **08.21 ~ 08.24** | **무선 영상 Ingest PoC + SQLD 일정 보호** | - **08.21~08.22:** SQLD 시험 대비를 우선하고 프로젝트 작업량 최소화<br>- 이 기간에는 자동 학습·Validation·Benchmark처럼 저개입 AI 작업만 허용<br>- **08.23~08.24:** 선택한 영상 송출 경로의 PC 수신 시험 본격 재개<br>- Edge AI 입력 Adapter/Receiver 구성<br>- reconnect·buffer·frame drop 확인<br>- 기존 smartphone/browser ingest와 인터페이스 비교 | - SQLD 일정 침해 없이 프로젝트 지속<br>- Edge PC에서 실기체 또는 실기체 중계 영상 프레임 수신<br>- 안정적인 재연결 절차 확보 | 🔵 **예정** |
| **08.25 ~ 08.27** | **AI 영상 추론 고도화 통합** | - 기본 Detection 모델을 `yolo26m.pt` 중심으로 재구성하고 `best.pt` 전문 탐지와 역할 분리<br>- Detection → Tracking → 선택적 Pose/Segmentation의 단계형 inference orchestration 구현<br>- 사람/위험 후보 ROI에 Pose를 선택 적용하고 필요 장면에 Segmentation을 선택 적용해 GPU 부하 제어<br>- VisDrone 기반 원거리·소형 객체 탐지 보완 실험<br>- 고해상도 입력, 타일 추론 및 small-object 대응 설정 비교<br>- snapshot/video evidence 및 Event schema에 track id·pose·mask 결과 반영 검토<br>- FPS·p50/p95 inference latency·drop rate·VRAM·Precision/Recall·mAP 기록 | - `yolo26m.pt` 실시간 기준선 확보<br>- Tracking ID 지속성 확인<br>- Pose/Seg 결과 관제 화면 또는 Event에서 확인<br>- `best.pt` 개선 모델 검증<br>- 원거리·소형 객체 개선 전/후 비교 Evidence 확보 | 🔵 **예정** |
| **08.28 ~ 08.31** | **실기체 관제 Session / Telemetry 통합** | - 비행 세션과 영상·AI Event 연계<br>- 실제 또는 확보 가능한 비행 데이터 Adapter 연결<br>- 위치·고도·방향·속도 등 관제 데이터 정규화<br>- MySQL 저장 및 지도·경로 재생 회귀 검증 | - 하나의 Flight Session에서 Telemetry + AI Event 추적 가능<br>- DB/대시보드 E2E 확인 | 🔵 **예정** |
| **09.01 ~ 09.03** | **AWS Hybrid 선택 확장 / Core Debug Buffer** | **GO:** Edge AI Event/Telemetry → AWS 최소 API·로그·저장 검증<br>**NO-GO:** AWS 종료 후 DJI/Edge/관제 Debug에 전 시간 투입<br>- AWS GPU/EKS/SageMaker는 본 일정의 필수 범위에서 제외 | - GO 시 Edge → AWS 실데이터 전달 Evidence<br>- NO-GO 시 Core E2E 차단 이슈 해소 | 🟠 **선택 확장** |
| **09.04 ~ 09.06** | **통합 QA / 보안 / 배포 회귀** | - RBAC·세션·QR Pairing·HTTPS 회귀 검증<br>- Docker Hub Release 및 Private CD Preflight 확인<br>- 실제 CD·Health Check·Rollback 회귀<br>- 장애 시 복구 시간 측정 | - 전 서비스 healthy<br>- 주요 E2E 및 Rollback PASS | 🔵 **예정** |
| **09.07 ~ 09.08** | **현장 시연 시나리오 고정** | - 정상 시나리오 1개를 최우선으로 고정<br>- 영상·Telemetry·AI·Dashboard 동시 시연<br>- 네트워크/실기체 장애 시 대체 시연 경로 준비 | - 1회 이상 End-to-End 리허설 PASS<br>- 대체 시연 절차 준비 | 🔵 **예정** |
| **09.09** | **발표·문서·Evidence 정리** | - README/Architecture/일정표 현행화<br>- Demo 캡처·영상·CI/CD Evidence 선별<br>- 구현/선택확장/미완료 항목 명확히 구분 | - GitHub 문서 최신화<br>- 발표 자료 Evidence 준비 | 🔵 **예정** |
| **09.10** | **Feature Freeze / 최종 리허설** | - 신규 기능 추가 중단<br>- 발표 PC·네트워크·Drone·배터리 점검<br>- 전체 시나리오 반복 리허설<br>- DB/로그/복구 상태 확인 | - Critical issue 0<br>- 최종 리허설 PASS | 🔵 **예정** |
| **09.11** | **3차 프로젝트 최종 시연·발표** | - 실기체/무선 영상/Edge AI/관제 통합 결과 시연<br>- CI/CD·Rollback 및 Hybrid 설계 결과 설명<br>- 기술적 한계와 후속 확장 방향 정리 | - 최종 발표 및 산출물 제출 | 🔵 **예정** |

---

## ☁️ AWS Spike Go / No-Go Gate

AWS는 3차 프로젝트의 필수 성공 조건이 아니라 **Edge–Cloud 확장 가능성 검증 항목**입니다.

### GO 조건

- Edge PC → AWS EC2 API 통신 성공
- VisionFlow 형태 JSON Event 전달 및 서버 로그 확인
- 4~6시간 이내에 네트워크·보안·Docker 운용이 감당 가능한 수준으로 판단
- DJI / Edge AI P0 일정에 영향이 없음

### NO-GO 조건

- IAM / Security Group / 네트워크 문제만으로 과도한 시간 소비
- AWS 구현이 DJI 실기체·Edge AI 일정에 영향을 주기 시작함
- GPU quota·비용·운영 복잡도가 프로젝트 가치보다 커짐
- 안정적 시연 경로를 위협함

> **NO-GO도 정상적인 기술 의사결정입니다.** 이 경우 실시간 AI는 Edge GPU에 유지하고 AWS는 후속 확장 범위로 기록합니다.

---

## 🔒 일정 관리 원칙

1. **P0 Core 우선:** DJI → Edge GPU → **Detection + Tracking + 선택적 Pose/Segmentation + 원거리 소형 객체 대응** → Telemetry/Event → Dashboard를 먼저 완성합니다.
2. **AWS는 Optional:** GO Gate 통과 후에도 Core 일정에 여유가 있을 때만 확장합니다.
3. **Feature Freeze:** 09.10부터 신규 기능을 추가하지 않습니다.
4. **Recovery First:** 실기체·네트워크 장애를 고려해 항상 대체 시연 경로를 유지합니다.
5. **매일 현행화:** 실제 진행 결과에 따라 본 일정표의 상태와 Evidence를 갱신합니다.
