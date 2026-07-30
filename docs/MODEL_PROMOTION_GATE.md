# VisionFlow `best.pt` 모델 승격 게이트

## 목적

HP OMEN 활성화, 동일 영상 A/B 성능 비교, 고정 데이터셋 정확도 평가를 하나의
읽기 전용 판정으로 연결합니다. 모델 파일을 복사하거나 환경설정을 바꾸지 않으며
MySQL·Docker·서비스도 변경하지 않습니다.

## 사전 조건

1. HP 최초 구동 결과가 `HP_OMEN_RUNTIME_READY_WITH_DEFERRED`
2. `yolo26n.pt`와 `best.pt`를 동일한 영상·설정으로 A/B 측정
3. `best.pt` 정확도 평가 시 최소 Precision·Recall·mAP 기준을 명시
4. 클래스 매핑 파일을 검토해 `VALID` 상태로 평가
5. 현재 모델이 `models\best.pt`에 존재

정확도 평가가 기준 없이 `MEASURED`인 경우 자동 승격하지 않습니다.

## 실행 계획만 확인

```bat
cd /d C:\VisionFlow-Drone
scripts\run-visionflow-model-promotion.bat plan
```

## HP OMEN에서 자동 판정

표준 경로의 최신 활성화·A/B 비교·정확도 보고서를 자동 선택합니다.

```bat
scripts\run-visionflow-model-promotion.bat evaluate
```

정상 승격 결과:

```text
VisionFlow model promotion: MODEL_PROMOTION_READY
```

사람의 검토가 필요한 결과:

```text
VisionFlow model promotion: MODEL_PROMOTION_REVIEW_REQUIRED
```

`TRADE_OFF`, 기준 모델 우세, 낮은 입력 부하 경고가 있으면 정확도 기준을 통과했더라도
자동 승격하지 않습니다.

차단 결과:

```text
VisionFlow model promotion: MODEL_PROMOTION_BLOCKED
```

모델 SHA-256 불일치, 무효한 성능 비교, 정확도 기준 미설정·실패, 미승인 클래스
매핑, 라벨 누락, CPU 정확도 평가, 오래된 증적 중 하나가 원인입니다.

## 보고서

```text
artifacts\model-promotion\promotion-<UTC 시각>\
  visionflow-model-promotion.json
  visionflow-model-promotion.html
  visionflow-model-promotion.sha256
```

## 독립 검증

```bat
scripts\run-visionflow-model-promotion-verify.bat ^
  --report artifacts\model-promotion\promotion-<UTC 시각>\visionflow-model-promotion.json
```

독립 검증기는 입력 보고서 3개, 현재 `best.pt`, 모델 SHA-256, 판정 정책,
JSON·HTML·sidecar를 다시 계산합니다.

## 직접 보고서 지정

자동 선택 대신 실제 경로를 지정할 수도 있습니다.

```bat
scripts\run-visionflow-model-promotion.bat evaluate ^
  --activation artifacts\hp-omen-restore\activation-...\visionflow-hp-omen-activation.json ^
  --comparison artifacts\ai-benchmark-comparison\visionflow-ai-comparison-....json ^
  --accuracy artifacts\model-evaluation\best-...\evaluation-report.json
```

기본 최신성 제한은 활성화 24시간, 성능 비교 24시간, 정확도 평가 7일입니다.

## 승격 승인 이후

`MODEL_PROMOTION_READY`가 나온 뒤에는 원본 `.env.docker`를 직접 고치지 말고 모델
릴리스·자동 롤백 게이트를 사용합니다.

```bat
scripts\run-visionflow-model-release.bat prepare
```

상세 절차는 `docs\MODEL_RELEASE_ROLLBACK.md`를 확인하세요.
