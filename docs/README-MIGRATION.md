# VisionFlow 안전 소스 릴리스

- 생성 시각: `2026-07-28T04:03:39.086008+00:00`
- 소스 파일: 790개
- 소스 용량: 4594130 bytes
- 제외 항목: 27개

## HP OMEN 재구축 순서

1. ZIP을 새 작업 폴더에 풉니다.
2. `.env.example`을 참고해 새 `.env.docker`를 직접 만듭니다.
3. 검증된 MySQL 백업 ZIP은 별도 보안 경로로 복사합니다.
4. `best.pt`는 별도 모델 경로로 복사하고 체크섬을 기록합니다.
5. `docker compose --env-file .env.docker up --build -d`를 실행합니다.
6. acceptance와 release gate를 새 장비에서 다시 실행합니다.

실제 `.env`, 데이터베이스, 백업, 모델 가중치, 영상은 이 ZIP에 없습니다.
스마트폰 실센서와 GPU/`best.pt` 성능 검증은 새 환경에서 별도로 진행합니다.
DJI Mini 4 Pro 전용 연동은 3차 프로젝트 범위입니다.
