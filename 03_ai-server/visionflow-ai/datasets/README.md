# VisionFlow YOLO 검증 데이터셋

학습에 사용한 데이터셋의 **검증용 이미지와 라벨**을 이 폴더 아래에 둡니다.
실제 데이터는 Git과 Docker 이미지에 포함되지 않습니다.

권장 구조:

```text
datasets/
└─ visionflow/
   ├─ data.yaml
   ├─ images/
   │  └─ val/
   └─ labels/
      └─ val/
```

`data.yaml` 예시:

```yaml
path: .
train: images/train
val: images/val
names:
  0: person
  1: car
```

모델을 평가할 때는 저장소 루트에서 다음 명령을 사용합니다.

```bat
scripts\run-visionflow-model-evaluation.bat -ModelFile best.pt -DataYaml visionflow/data.yaml
```
