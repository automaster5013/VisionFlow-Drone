# VisionFlow 보안 구성 Fail-Fast 가이드

VisionFlow의 표준 Docker Compose 실행은 운영자 RBAC와 AI 내부 서비스 인증을
기본 활성화 상태로 사용합니다. 다음 네 값은 모두 필수이며 서로 달라야 합니다.

- `VISIONFLOW_VIEWER_KEY`
- `VISIONFLOW_OPERATOR_KEY`
- `VISIONFLOW_ADMIN_KEY`
- `VISIONFLOW_AI_INTERNAL_KEY`

각 키는 최소 32자 이상이어야 하며, 로컬·발표 환경에서는 32바이트 난수의
64자리 16진수 값을 권장합니다. `.env`와 로컬 credentials 파일은 Git에
커밋하거나 채팅·스크린샷에 공유하지 않습니다.

## 준비 순서

1. `.env.example`을 `.env`로 복사합니다.
2. MySQL 비밀번호와 네 보안 키를 실제 값으로 교체합니다.
3. 보안 사전 검사를 실행합니다.
4. Compose 구성을 확인한 뒤 서비스를 시작합니다.

```bat
copy .env.example .env
python scripts\visionflow_config_preflight.py --root .
docker compose config --quiet
docker compose up -d
```

사전 검사는 키 값 자체를 출력하거나 파일에 다시 쓰지 않습니다. 존재 여부,
길이, 중복 선언, placeholder 사용, 키 재사용만 검사합니다.

## 64자리 키 생성 예시

다음 PowerShell 명령은 새 64자리 키를 클립보드에만 복사합니다.

```powershell
$bytes = New-Object byte[] 32
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
$rng.GetBytes($bytes)
$rng.Dispose()
$key = -join ($bytes | ForEach-Object { $_.ToString('x2') })
$key | Set-Clipboard
Write-Host ('새 키를 클립보드에 복사했습니다. 길이=' + $key.Length)
```

네 키를 각각 별도로 생성해 `.env`에 입력합니다. 같은 값을 두 역할이나
AI 내부 인증에 재사용하지 않습니다.

## Fail-Fast 동작

`compose.yaml`은 필수 키가 없거나 비어 있으면 컨테이너를 재생성하기 전에
`docker compose config` 또는 `docker compose up` 단계에서 중단합니다.
이 정책은 다음 장애를 예방합니다.

- Backend의 `OperatorCredentialRegistry` 초기화 실패와 재시작 루프
- Frontend의 AI 내부 키 누락으로 인한 반복 `502 Bad Gateway`
- AI 서버와 Frontend 사이의 내부 키 불일치
- 역할별 키 재사용으로 인한 권한 경계 혼동

## 안전한 운영 원칙

- `docker compose down -v`는 MySQL 영속 볼륨을 제거할 수 있으므로 복구
  과정에서 사용하지 않습니다.
- 환경변수를 변경한 뒤에는 필요한 서비스만 `--no-deps --force-recreate`로
  재생성합니다.
- 키 값은 로그에 출력하지 않고 존재 여부와 길이만 점검합니다.
- 발표 전 Release Gate에서 사전 검사와 역할별 수동 인수검사를 다시 수행합니다.
