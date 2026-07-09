# K-Startup 모집중 공고 Slack 알림 스케줄러

K-Startup의 `사업공고 > 모집중 > 중앙부처ㆍ지자체ㆍ공공기관` 공고를 API로 조회하고 Slack으로 알림을 보내는 1개 사이트 전용 예제입니다.

처음에는 이 프로젝트 하나만 정상 동작시키고, 나중에 다른 사이트 수집기를 추가해서 통합하는 방식으로 진행하면 됩니다.

## 1. 준비물

1. 공공데이터포털 API 인증키
   - API명: `창업진흥원_K-Startup(사업소개,사업공고,콘텐츠 등)_조회서비스`
   - 상세 기능: `지원 사업 공고 정보`
2. Slack Incoming Webhook URL

## 2. 로컬 실행 순서

### 1) 패키지 설치

```powershell
python -m pip install -r requirements.txt
```

### 2) 설정파일 복사

```powershell
copy config.example.yaml config.yaml
copy .env.example .env
```

Mac/Linux는 아래처럼 실행합니다.

```bash
cp config.example.yaml config.yaml
cp .env.example .env
```

### 3) config.yaml 수정

`config.yaml`에서 `kstartup.api_url`에 공공데이터포털 Swagger/활용가이드의 `지원 사업 공고 정보` 요청 URL을 입력합니다.

```yaml
kstartup:
  api_url: "여기에 API 요청 URL 입력"
```

API 파라미터명은 공공데이터포털 Swagger/활용가이드와 다를 수 있습니다. 응답이 안 오면 `params`, `ongoing_param_candidates`, `field_candidates`를 문서에 맞춰 조정하세요.

### 4) .env 수정

`.env`에 아래 값을 넣습니다.

```env
KSTARTUP_SERVICE_KEY=공공데이터포털_인증키
SLACK_WEBHOOK_URL=Slack_Webhook_URL
```

### 5) 실행

```powershell
python main.py
```

## 3. GitHub Actions 실행

`.github/workflows/kstartup_notice.yml`이 포함되어 있습니다.

기본 실행 시간은 한국시간 매주 월요일 오전 11시입니다.

```yaml
cron: "0 2 * * 1"
```

GitHub 저장소의 아래 경로에 Secrets를 등록하세요.

```text
Settings
→ Secrets and variables
→ Actions
→ New repository secret
```

필요한 Secret은 2개입니다.

| Secret 이름 | 설명 |
|---|---|
| KSTARTUP_SERVICE_KEY | 공공데이터포털 인증키 |
| SLACK_WEBHOOK_URL | Slack Incoming Webhook URL |

## 4. 신규/기존 구분 방식

`seen_notice_ids.json`에 이미 확인한 공고 ID를 저장합니다.

- 처음 보는 공고: `[신규]`
- 이전에 본 공고: `[기존]`

GitHub Actions 실행 후 `seen_notice_ids.json`은 자동으로 commit/push 되도록 설정되어 있습니다.

## 5. 파일 구성

```text
kstartup_slack_scheduler/
├─ main.py
├─ kstartup_fetch.py
├─ notifier.py
├─ config.example.yaml
├─ .env.example
├─ requirements.txt
├─ seen_notice_ids.json
├─ .gitignore
├─ README.md
└─ .github/
   └─ workflows/
      └─ kstartup_notice.yml
```

## 6. 주의사항

- `.env`와 `config.yaml`은 GitHub에 올리지 마세요.
- `seen_notice_ids.json`은 신규/기존 구분을 위해 GitHub에 올려도 됩니다.
- API의 실제 요청 URL과 파라미터명은 공공데이터포털의 Swagger/활용가이드에서 확인 후 맞춰야 합니다.
