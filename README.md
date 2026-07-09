# 정부지원사업 공고 모니터링 스케줄러

아래 4개 URL에서 현재 접수중/모집중인 사업공고를 수집하고, 중복된 사업명은 1개로 정리해서 이메일로 발송하는 파이썬 프로그램입니다.

1. 기업마당 기술 분야
2. 기업마당 창업 분야
3. K-Startup 모집중 공고
4. SMTECH 사업공고

## 1. 로컬 PC에서 실행하는 방법

### 1) 패키지 설치

```bash
pip install -r requirements.txt
```

### 2) 설정파일 만들기

`config.example.yaml` 파일을 복사해서 `config.yaml`로 이름을 바꿉니다.

```bash
copy config.example.yaml config.yaml
```

Mac/Linux는 아래 명령어를 사용합니다.

```bash
cp config.example.yaml config.yaml
```

### 3) 이메일 정보 설정

`config.yaml` 안의 이메일 정보를 수정합니다.

```yaml
notification:
  method: "email"
  email:
    smtp_host: "smtp.gmail.com"
    smtp_port: 587
    sender: "보내는이메일@gmail.com"
    receiver: "받는이메일@example.com"
    password: "앱비밀번호"
```

Gmail을 사용할 경우 일반 로그인 비밀번호가 아니라, Google 계정의 `앱 비밀번호`를 사용하는 것이 좋습니다.

### 4) 실행

```bash
python main.py
```

첫 실행 때는 이전 발송 이력이 없으므로 수집된 공고가 한 번에 많이 보일 수 있습니다. 이후부터는 `seen_urls.json`에 저장된 URL을 기준으로 새 공고만 발송합니다.

## 2. GitHub Actions에서 매주 월요일 11시에 자동 실행

이 프로젝트에는 `.github/workflows/weekly_notice.yml` 파일이 포함되어 있습니다.

한국시간 매주 월요일 11시는 UTC 기준 월요일 02시이므로 cron은 아래와 같습니다.

```yaml
cron: "0 2 * * 1"
```

GitHub 저장소에 올린 뒤, 아래 값을 `Settings > Secrets and variables > Actions > Secrets`에 등록하세요.

| Secret 이름 | 설명 |
|---|---|
| SMTP_HOST | 예: smtp.gmail.com |
| SMTP_PORT | 예: 587 |
| SMTP_SENDER | 보내는 이메일 |
| SMTP_RECEIVER | 받는 이메일 |
| SMTP_PASSWORD | 이메일 앱 비밀번호 |

## 3. 파일 구성

```text
biz_notice_monitor/
├─ main.py
├─ config.example.yaml
├─ requirements.txt
├─ README.md
├─ .gitignore
└─ .github/
   └─ workflows/
      └─ weekly_notice.yml
```

## 4. 중복 제거 방식

사업명에서 공백, 괄호, 특수문자, `2026년`, `모집`, `공고`, `지원사업` 같은 반복 표현을 제거한 뒤 비교합니다.

또한 완전 일치하지 않아도 유사도가 높으면 같은 공고로 보고 1개만 표시합니다.

## 5. 주의사항

정부 사이트의 HTML 구조가 바뀌면 일부 공고가 누락될 수 있습니다. 사이트가 JavaScript로 목록을 불러오는 방식으로 바뀌면 내부 API 확인 또는 Playwright/Selenium 방식으로 보완해야 합니다.

`config.yaml`에는 이메일 비밀번호가 들어갈 수 있으므로 GitHub에 올리지 마세요. `.gitignore`에 이미 포함되어 있습니다.
