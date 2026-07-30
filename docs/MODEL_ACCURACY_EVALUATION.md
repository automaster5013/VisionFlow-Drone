# VisionFlow `best.pt` 정확도 평가 가이드

## 1. 이번 단계의 목적

실시간 영상 처리 속도와 모델 정확도는 서로 다른 검증 항목입니다. 기존 A/B 벤치마크가
지연 시간, 처리 FPS, 프레임 누락을 비교했다면 이번 패치는 고정된 YOLO 검증 데이터셋으로
다음 항목을 산출합니다.

- 전체 Precision, Recall, mAP50, mAP75, mAP50-95
- 클래스별 Precision, Recall, F1, AP50, AP50-95
- 클래스별 추정 TP/FP/FN
- 이미지별 TP/FP/FN과 오류가 큰 이미지 순위
- 원본/정규화 혼동행렬과 Ultralytics PR/F1 곡선
- 모델 SHA-256, 데이터셋 지문, CUDA/GPU/라이브러리 버전
- VisionFlow 백엔드 관제 이벤트용 클래스 매핑 검토 템플릿

스마트폰 카메라가 없어도 수행할 수 있습니다.

## 2. 반영 파일과 전체 경로

저장소 루트가 `C:\VisionFlow-Drone`일 때 다음 파일을 반영합니다.

| 파일 | 전체 경로 |
|---|---|
| 정확도 평가 모듈 | `C:\VisionFlow-Drone\03_ai-server\visionflow-ai\app\model_evaluation.py` |
| 단위 테스트 | `C:\VisionFlow-Drone\03_ai-server\visionflow-ai\tests\test_model_evaluation.py` |
| Python 의존성 | `C:\VisionFlow-Drone\03_ai-server\visionflow-ai\requirements.txt` |
| 데이터셋 안내 | `C:\VisionFlow-Drone\03_ai-server\visionflow-ai\datasets\README.md` |
| AI Docker 제외 규칙 | `C:\VisionFlow-Drone\03_ai-server\visionflow-ai\.dockerignore` |
| AI Git 제외 규칙 | `C:\VisionFlow-Drone\03_ai-server\visionflow-ai\.gitignore` |
| 기본 Compose | `C:\VisionFlow-Drone\compose.yaml` |
| GPU Compose 오버레이 | `C:\VisionFlow-Drone\compose.gpu.yaml` |
| PowerShell 실행기 | `C:\VisionFlow-Drone\scripts\visionflow-model-evaluation.ps1` |
| 배치 실행기 | `C:\VisionFlow-Drone\scripts\run-visionflow-model-evaluation.bat` |

기존 파일은 ZIP 안의 동명 파일 전체를 무조건 덮어쓰기보다, 현재 저장소에 이미 반영된
이전 패치를 보존하면서 변경 내용을 병합하는 것이 안전합니다.

## 3. 모델과 데이터셋 배치

모델:

```text
C:\VisionFlow-Drone\03_ai-server\visionflow-ai\models\best.pt
```

검증 데이터셋 권장 구조:

```text
C:\VisionFlow-Drone\03_ai-server\visionflow-ai\datasets\visionflow\
├─ data.yaml
├─ images\val\...
└─ labels\val\...
```

`data.yaml`의 `names`는 `best.pt`에 내장된 클래스 ID와 이름이 정확히 같아야 합니다.
다르면 잘못된 클래스별 지표를 막기 위해 평가가 즉시 중단됩니다. 학습 이미지가 아니라
학습에 사용하지 않은 검증 또는 테스트 split을 사용해야 합니다.

실제 모델과 데이터셋은 `.gitignore`와 `.dockerignore`로 제외되며 Docker 이미지 안에
복사되지 않습니다. Compose가 읽기 전용 볼륨으로 연결합니다.

## 4. HP OMEN RTX 5060에서 실행

Docker Desktop, 최신 NVIDIA 드라이버 및 GPU 컨테이너 사용 환경을 먼저 준비한 뒤 저장소
루트에서 실행합니다.

```bat
scripts\run-visionflow-model-evaluation.bat -ModelFile best.pt -DataYaml visionflow/data.yaml
```

첫 실행은 CUDA용 PyTorch 이미지 빌드 때문에 오래 걸릴 수 있습니다. 이미 빌드한 이미지가
있다면 다음부터 `-SkipBuild`를 사용할 수 있습니다.

```bat
scripts\run-visionflow-model-evaluation.bat -ModelFile best.pt -DataYaml visionflow/data.yaml -SkipBuild
```

GPU 메모리가 부족하면 `-Batch 4` 또는 `-Batch 2`로 줄입니다. 정확한 A/B 비교에서는
모델 외에 `ImageSize`, `Batch`, split, 데이터셋 지문을 동일하게 유지해야 합니다.

## 5. LG GRAM CPU에서 선택적으로 실행

CPU 기준 확인이 꼭 필요할 때만 실행합니다.

```bat
scripts\run-visionflow-model-evaluation.bat -ModelFile best.pt -DataYaml visionflow/data.yaml -Cpu -Batch 1 -Workers 2
```

정확도 값은 같은 데이터와 설정에서 비교할 수 있지만 CPU 검증은 매우 오래 걸릴 수
있습니다. LG GRAM에서는 모듈 단위 검증까지만 완료하고 실제 전체 평가는 OMEN에서 수행해도
됩니다.

## 6. 결과 확인

실행 결과는 다음 위치에 실행 시각별로 생성됩니다.

```text
C:\VisionFlow-Drone\artifacts\model-evaluation\best-YYYYMMDDTHHMMSSZ\
```

주요 파일:

- `README.md`: 사람이 바로 확인하는 요약
- `evaluation-report.json`: 재현 정보와 전체 결과
- `per-class-metrics.csv`: 클래스별 정량 지표
- `worst-image-errors.csv`: 오탐/미탐 우선 검토 목록
- `confusion-matrix.json`: 원본 및 정규화 혼동행렬
- `class-mapping.template.json`: 관제 클래스 매핑 검토용 템플릿
- `ultralytics/`: confusion matrix, PR/F1 곡선 등 기본 결과

`tp/fp/fn`은 Ultralytics 혼동행렬에서 계산하며 `countSource`가 `confusion_matrix`인지
확인합니다. 라이브러리 버전 차이로 혼동행렬 원본이 없으면 최적 F1 지점의 P/R에서 계산한
참고값으로 대체되고 `optimal_pr_estimate`로 표시됩니다. 정확한 혼동 구조는
`confusion-matrix.json`과 Ultralytics 플롯을 함께 확인합니다.

## 7. 클래스 매핑 승인 절차

현재 백엔드 위험 판정은 다음 표준 이름을 중대 클래스 후보로 사용합니다.

```text
fire, smoke, gun, knife, weapon, accident, fight
```

평가가 만든 템플릿을 데이터셋 폴더로 복사합니다.

```text
03_ai-server\visionflow-ai\datasets\visionflow\class-mapping.json
```

각 클래스의 실제 의미를 확인한 뒤에만 다음처럼 수정합니다.

```json
{
  "sourceClassId": 3,
  "sourceClassName": "flame",
  "canonicalName": "fire",
  "enabled": true,
  "minConfidence": 0.6,
  "reviewStatus": "APPROVED",
  "notes": "학습 데이터 라벨 정의 확인 완료"
}
```

검증 명령:

```bat
scripts\run-visionflow-model-evaluation.bat -ModelFile best.pt -DataYaml visionflow/data.yaml -ClassMapping visionflow/class-mapping.json -RequireApprovedMapping -SkipBuild
```

클래스 의미를 추측해 연결하면 잘못된 사고 경보를 만들 수 있습니다. 이번 단계는 템플릿과
검증까지만 제공하며, 승인된 매핑을 AI 실시간 이벤트에 적용하는 작업은 다음 단계에서
진행합니다.

## 8. 품질 기준선 고정

첫 실행은 임의의 합격선을 넣지 않고 `MEASURED`로 기록합니다. 실제 기준값을 정한 후에는
다음처럼 자동 합격/불합격 판정을 사용할 수 있습니다.

```bat
scripts\run-visionflow-model-evaluation.bat -ModelFile best.pt -DataYaml visionflow/data.yaml -MinPrecision 0.70 -MinRecall 0.65 -MinMap50 0.75 -MinMap50_95 0.50 -SkipBuild
```

위 숫자는 문법 예시일 뿐 프로젝트의 확정 기준값이 아닙니다. 실제 `best.pt`의 최초 보고서,
오탐 허용 수준, 관제 목적을 확인한 뒤 기준을 합의해야 합니다.

## 9. 코드 검증

AI 폴더에서 실행합니다.

```bat
cd C:\VisionFlow-Drone\03_ai-server\visionflow-ai
python -m pytest tests\test_model_evaluation.py
python -m compileall app\model_evaluation.py
```

Windows 애플리케이션 제어 정책이 Ruff 실행 파일을 막는 환경에서는 Ruff보다 위 단위 테스트와
Docker 이미지 내부 검증을 우선 사용할 수 있습니다.

## 참고

- Ultralytics 검증 모드: <https://docs.ultralytics.com/modes/val/>
- Ultralytics 검증 지표 구현: <https://github.com/ultralytics/ultralytics/blob/main/ultralytics/utils/metrics.py>
