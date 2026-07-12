# K-Startup Email Scheduler

K-Startup 지원사업 공고 API에서 모집중 공고를 조회하고, 신규 공고를 HTML 이메일로 발송하는 프로그램입니다.

HTML 본문내용 발송 & HTML 문서 첨부 발송


## 주요 기능

- K-Startup API 공고 조회
- 분류 필터: 사업화, 인력, 멘토링ㆍ컨설팅ㆍ교육
- 마감 공고 제외
- 신규/기존 공고 구분
- 신규 공고만 HTML 표 형태로 이메일 발송
- GitHub Actions 주간 자동 실행 지원

## 로컬 실행

```powershell
copy .env.example .env
python -m pip install -r requirements.txt
python main.py
```

`.env`에 실제 값을 넣어야 합니다.

## GitHub Secrets

아래 Secrets를 등록하세요.

- `KSTARTUP_SERVICE_KEY`
- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USE_TLS`
- `SMTP_USER`
- `SMTP_PASSWORD`
- `MAIL_FROM`
- `MAIL_TO`
- `MAIL_CC` 선택

## 주의

`.env`, `config.yaml`, `latest_notices.json`은 GitHub에 올리지 마세요.
