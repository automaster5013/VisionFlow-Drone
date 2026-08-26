# VisionFlow 모델 계약

오프라인 발표와 Docker GPU 모드에서 사용하는 가중치는 이 폴더에 두며, 모델 역할별 파일명을 고정합니다. `best.pt`처럼 출처와 역할을 알 수 없는 이름으로 보관하지 않습니다.

| 역할 | 프로필 | 고정 파일명 | 활성화 정책 |
|---|---|---|---|
| 일반 객체 Detection | `GENERAL_LIVE` | `yolo26m.pt` | 일반 실시간 기준선 |
| VisDrone 1차 전이학습 | `AERIAL_SMALL_OBJECT_LIVE` | `yolo26m-visdrone-s1-best.pt` | 계약·평가 전용, LIVE 금지 |
| VisDrone + 발표환경 2차 전이학습 | `AERIAL_SMALL_OBJECT_LIVE` | `yolo26m-visdrone-s2-best.pt` | 매니페스트 통과 후 LIVE 허용 |
| PPE 전문 판정 | 별도 PPE 파이프라인 | `ppe-yolo26m-best.pt` | VisDrone 가중치로 대체 금지 |

`DETERMINISTIC_COMPARE`는 단일 가중치 역할이 아닙니다. 동일 프레임에서 `GENERAL_LIVE`와 `AERIAL_SMALL_OBJECT_LIVE` 결과를 비교하는 Small Object Showdown 오케스트레이션 프로필입니다.

## LIVE 런타임 선택

일반 객체 기준선은 다음 세 값을 사용합니다.

```dotenv
AI_MODEL_PROFILE=GENERAL_LIVE
AI_MODEL_PATH=models/yolo26m.pt
AI_MODEL_PROFILES_PATH=config/model-profiles-v1.json
```

VisDrone S2 LIVE는 실가중치 매니페스트까지 함께 지정해야 합니다.

```dotenv
AI_MODEL_PROFILE=AERIAL_SMALL_OBJECT_LIVE
AI_MODEL_PATH=models/yolo26m-visdrone-s2-best.pt
AI_MODEL_MANIFEST_PATH=models/manifests/yolo26m-visdrone-s2-best.manifest.json
AI_MODEL_PROFILES_PATH=config/model-profiles-v1.json
```

서버 시작 시 레지스트리, S2 활성화 자격, 가중치 파일명·SHA-256·크기와 원본 10개 클래스가 모두 일치해야 합니다. `pedestrian`과 `people`은 Track ID 연계용 `person/HUMAN`으로, `motor`는 이벤트용 `motorcycle/CYCLE`로 정규화합니다. PPE 모델 결과에는 이 매핑을 적용하지 않습니다. 기존 `yolo26n-cpu`와 `best-gpu`는 마이그레이션을 위한 호환 모드로 유지됩니다.

## Small Object Showdown

`DETERMINISTIC_COMPARE`는 결정론적 더미영상만 허용하며, 디코딩된 동일 프레임의 복사본을 `GENERAL_LIVE` 기준선과 `AERIAL_SMALL_OBJECT_LIVE` 후보에 고정 순서로 전달합니다.

```dotenv
AI_SOURCE_TYPE=DUMMY_VIDEO
AI_MODEL_PROFILE=DETERMINISTIC_COMPARE
AI_COMPARE_BASELINE_MODEL_PATH=models/yolo26m.pt
AI_COMPARE_CANDIDATE_MODEL_PATH=models/yolo26m-visdrone-s2-best.pt
AI_COMPARE_CANDIDATE_MANIFEST_PATH=models/manifests/yolo26m-visdrone-s2-best.manifest.json
AI_MODEL_PROFILES_PATH=config/model-profiles-v1.json
AI_PHASE3_ENABLED=false
AI_REPORT_EVENTS=false
AI_SNAPSHOT_POLICY=OFF
```

두 모델은 같은 `AI_CONFIDENCE`, `AI_IOU`, `AI_IMAGE_SIZE`, `AI_DEVICE`를 사용합니다. 결과는 좌우 영상, 모델별 탐지 수와 평균·p50·p95·최대 지연, 전체 순차 비교 FPS, 후보 모델만 찾은 `area < 32² px` 객체의 `RECOVERED SMALL OBJECT` 표시로 제공합니다.

후보 단독 작은 객체 수는 정답 라벨이 없는 런타임의 `MODEL_DIFFERENCE_PROXY`입니다. 이를 Recall 또는 미탐률로 해석하지 않습니다. 실제 작은 객체 Recall·미탐률은 학습에서 제외한 라벨 보유 영상 단위 검증 세트로 별도 평가합니다.

VRAM은 두 모델이 같은 프로세스에 동시에 적재된 상태의 CUDA allocated/reserved/max allocated 값입니다. 프레임 단위 메모리 할당을 모델별 VRAM으로 잘못 분리해 표시하지 않습니다. BoT-SORT Track ID 비교, ROI 확대 및 추적 유지 증거는 다음 상세 단계에서 추가합니다.

## 라벨 기반 Small-Object 평가

Phase 2B-4 평가 계약은 `FINAL_HELDOUT` 정답 라벨과 IoU 0.5의 클래스별 결정론적 일대일 매칭으로 TP/FP/FN, Recall, 미탐률과 클래스별 지표를 생성합니다. 지표 provenance는 `LABELED_HELD_OUT_GROUND_TRUTH`로 고정하며, 런타임 Showdown의 `MODEL_DIFFERENCE_PROXY`와 분리합니다.

COCO 기준선은 VisDrone과 공통인 `person`, `bicycle`, `car`, `truck`, `bus`, `motorcycle`만 평가 대상으로 사용합니다. COCO에 없는 `van`, `tricycle`, `awning-tricycle` 정답은 기준선 미탐으로 남고, 후보 VisDrone 모델은 10개 원본 클래스를 표준 canonical mapping으로 평가합니다. 따라서 서로 다른 taxonomy를 같은 클래스 ID로 직접 비교하지 않습니다.

평가 보고서는 다음 증거를 함께 보관합니다.

- 두 모델의 전체·작은 객체 TP/FP/FN, Precision/Recall/미탐률과 클래스별 결과
- 후보가 기준선 미탐에서 복구한 실제 작은 객체 수와 `missed-small-objects.csv`
- 동일 데이터셋 fingerprint와 영상 단위 split manifest SHA-256
- 모델별 평균·p50·p95·최대 지연, FPS와 순차 격리 실행 범위의 peak CUDA allocated/reserved
- 모델 파일 SHA-256과 후보 가중치 매니페스트 identity

오프라인 순차 평가는 입력 큐가 없으므로 드롭률을 0으로 꾸미지 않고 측정 불가로 기록합니다. 기존 `app.model_evaluation`의 Ultralytics P/R/mAP 결과와 이 작은 객체 증거를 함께 검토한 뒤에만 S2 실가중치 매니페스트의 최종 평가 필드를 채웁니다.

## 매니페스트

실가중치 옆에는 같은 stem의 매니페스트를 둡니다.

```text
models/
├─ yolo26m-visdrone-s1-best.pt
├─ yolo26m-visdrone-s2-best.pt
└─ manifests/
   ├─ yolo26m-visdrone-s1-best.manifest.json
   └─ yolo26m-visdrone-s2-best.manifest.json
```

`manifests/*.manifest.template.json`을 복사한 뒤 모든 `REPLACE_WITH_*` 값과 0인 학습·평가 값을 실제 측정값으로 채우고 `template`을 `false`로 바꿉니다. 다음 항목은 반드시 실제 값이어야 합니다.

- 가중치 크기와 SHA-256, 부모 가중치 SHA-256
- 데이터셋 버전·fingerprint와 영상 단위 split manifest SHA-256
- `imgsz`, epoch, batch, seed와 Python/Ultralytics/PyTorch/CUDA 버전
- Precision, Recall, mAP50, mAP50-95, 작은 객체 Recall·미탐률, 클래스별 지표

작은 객체는 원본 해상도에서 COCO 기준 `area < 32² px`로 고정합니다. 발표용 최종 검증영상은 학습에서 제외합니다.

## CPU 계약 사전점검

이 명령은 추론이나 GPU 실행 없이 가중치를 로드해 파일 identity, task, 클래스와 매니페스트를 검사합니다.

```bat
cd 03_ai-server\visionflow-ai
python -m app.model_preflight ^
  --root . ^
  --manifest models\manifests\yolo26m-visdrone-s2-best.manifest.json ^
  --weight models\yolo26m-visdrone-s2-best.pt ^
  --activation
```

S1은 `--activation` 없이 계약·평가 용도로만 검사합니다. S2 LIVE 활성화는 `--activation`을 포함해야 합니다.

## Docker GPU 사전점검

물리 GPU 및 Docker 실행 승인을 받은 뒤 저장소 루트에서 실행합니다.

```powershell
scripts\visionflow-gpu-preflight.ps1 `
  -ModelFile yolo26m-visdrone-s2-best.pt `
  -ModelProfile AERIAL_SMALL_OBJECT_LIVE `
  -ManifestFile yolo26m-visdrone-s2-best.manifest.json
```

GPU 점검은 호스트/컨테이너 SHA-256 일치뿐 아니라 S2 lineage, 10개 VisDrone 클래스, 데이터 분리 정책과 평가 지표까지 확인합니다. 모델은 이미지에 포함하지 않고 읽기 전용 `/app/models` 볼륨으로 연결합니다.

## 전이학습 계획 계약

Phase 2B-5는 학습을 실행하지 않고 S1/S2 입력과 공개 Ultralytics 인자를 검증해 readiness lock을 만듭니다. YOLO26가 도입된 Ultralytics 8.4.0 이상을 요구하며, 실제 설치 버전은 lock 증거에 그대로 기록합니다.

| 단계 | 부모 | 출력 | 데이터 구성 |
|---|---|---|---|
| `VISDRONE_S1` | `yolo26m.pt` | `yolo26m-visdrone-s1-best.pt` | `VISDRONE2019_DET` |
| `VISIONFLOW_S2` | `yolo26m-visdrone-s1-best.pt` + S1 매니페스트 | `yolo26m-visdrone-s2-best.pt` | `VISDRONE2019_DET` + `VISIONFLOW_PRESENTATION` |

```bat
scripts\run-visionflow-model-training-plan.bat ^
  --root . ^
  --plan config\visdrone-s2-training.plan.json ^
  --output artifacts\training-plans\visdrone-s2-ready.json
```

`--output`을 생략하거나 `--check-only`를 쓰면 파일을 만들지 않고 JSON만 출력합니다. 기존 readiness report는 덮어쓰지 않습니다. 보고서에는 계획·부모 가중치·S1 부모 매니페스트·data YAML·영상 split manifest의 SHA-256, train/val fingerprint, 설치된 Ultralytics 버전과 순서가 고정된 공개 학습 인자가 포함됩니다.

학습 인자는 `imgsz`, `epochs`, `batch`, `seed`, `device`, `workers`, `optimizer=MuSGD`, `patience`, `deterministic=true`, `amp`, `close_mosaic`, `cache`만 허용합니다. YOLO26 내부 checkpoint 인자인 `muon_w`, `sgd_w`, `cls_w`, `o2m`, `topk`는 사용자 인자가 아니므로 계획에서 차단합니다. NMS-free `END_TO_END`와 `ONE_TO_MANY_NMS`는 학습 후 동일 가중치의 추론 증거를 비교하는 모드이며 가짜 학습 head 전환 옵션으로 전달하지 않습니다.

readiness lock의 `trainingExecuted`, `gpuAccessed`, `dockerAccessed`, `torchImported`, `ultralyticsImported`는 모두 `false`입니다. 실제 `YOLO.train()` 실행, GPU batch 확정, 생성된 best 가중치와 매니페스트 승격은 별도 승인이 필요한 Phase 2B-6 범위입니다.
