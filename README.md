# 나라장터 엔진오일 입찰 알림 봇 🛢️

조달청 **나라장터 입찰공고정보서비스 OpenAPI** 를 주기적으로 조회해서,
**엔진오일·윤활유 관련 입찰공고**가 새로 올라오면 **텔레그램으로 알림**을 보내줍니다.
별도 서버 없이 **GitHub Actions** 스케줄로 자동 실행됩니다.

```
나라장터 OpenAPI ──(30분마다 조회)──> 키워드 필터 ──(신규 공고만)──> 텔레그램 알림
                                          └ 중복 방지: state/seen.json
```

## 동작 방식

- GitHub Actions가 **30분마다**(`5,35 * * * *`) 실행됩니다.
- 최근 `LOOKBACK_HOURS`(기본 48시간) 공고를 조회하고, 공고명에 키워드(`엔진오일`, `윤활유` 등)가 포함된 건을 찾습니다.
- 이미 알린 공고는 `state/seen.json` 에 기록되어 **다시 알리지 않습니다.**
- 새 공고만 텔레그램으로 발송합니다.

---

## 설정 방법 (3단계)

### 1) 공공데이터포털 API 키 발급

1. [공공데이터포털 - 조달청_나라장터 입찰공고정보서비스](https://www.data.go.kr/data/15129394/openapi.do) 접속
2. **활용신청** 클릭 → 승인(보통 즉시 ~ 수 분)
3. 마이페이지 → 오픈API → 인증키에서 **일반 인증키(Decoding)** 값을 복사 → `G2B_SERVICE_KEY`
4. (선택) 활용신청 상세의 **엔드포인트** 가 코드 기본값과 다르면 `G2B_API_BASE` 로 지정
   - 기본값: `https://apis.data.go.kr/1230000/as/BidPublicInfoService`

### 2) 텔레그램 봇 만들기

1. 텔레그램에서 [@BotFather](https://t.me/BotFather) 와 대화 → `/newbot` → 봇 토큰 발급 → `TELEGRAM_BOT_TOKEN`
2. 방금 만든 봇과 대화를 시작(아무 메시지나 전송)
3. **내 chat_id 확인**: 봇과 대화한 뒤 아래 URL을 브라우저에서 열어 `chat.id` 확인
   ```
   https://api.telegram.org/bot<봇토큰>/getUpdates
   ```
   → 나온 숫자를 `TELEGRAM_CHAT_ID` 로 사용 (그룹/채널로 받으려면 봇을 그 방에 추가 후 같은 방법으로 확인)

### 3) GitHub 저장소에 시크릿 등록

저장소 → **Settings → Secrets and variables → Actions → New repository secret** 에서 아래 3개 등록:

| 이름 | 값 |
|------|----|
| `G2B_SERVICE_KEY` | 공공데이터포털 일반 인증키(Decoding) |
| `TELEGRAM_BOT_TOKEN` | 텔레그램 봇 토큰 |
| `TELEGRAM_CHAT_ID` | 알림 받을 chat id |

선택 설정은 **Variables** 탭에 등록(없으면 기본값 사용):

| 이름 | 설명 | 예시 |
|------|------|------|
| `G2B_API_BASE` | 엔드포인트가 기본값과 다를 때 | `https://apis.data.go.kr/1230000/as/BidPublicInfoService` |
| `G2B_OPERATIONS` | 조회 대상(물품/용역/공사) | `getBidPblancListInfoThng,getBidPblancListInfoServc` |
| `SEARCH_KEYWORDS` | 검색 키워드(콤마구분) | `엔진오일,윤활유,엔진 오일` |
| `LOOKBACK_HOURS` | 조회 기간(시간) | `48` |

등록이 끝나면 **Actions 탭 → "나라장터 엔진오일 입찰 모니터링" → Run workflow** 로 한 번 수동 실행해 동작을 확인하세요.

---

## 로컬에서 테스트

```bash
pip install -r requirements.txt
cp .env.example .env          # 값 채우기
set -a; source .env; set +a

# 실제 전송 없이 콘솔 출력만 (키워드 매칭 확인용)
DRY_RUN=1 python -m nara_monitor.main

# 실제 텔레그램 전송
python -m nara_monitor.main
```

테스트 실행:

```bash
pip install pytest
pytest -q
```

---

## 키워드 / 조회 대상 바꾸기

- **키워드**: `SEARCH_KEYWORDS` 변수(콤마구분)로 덮어쓰거나, `nara_monitor/config.py` 의 `DEFAULT_KEYWORDS` 수정
- **물품 외 용역/공사도 보기**: `G2B_OPERATIONS` 에 operation 추가
  - 물품 `getBidPblancListInfoThng`, 용역 `getBidPblancListInfoServc`, 공사 `getBidPblancListInfoCnstwk`
- **알림 주기**: `.github/workflows/naramarket-monitor.yml` 의 `cron` 수정

## 구성

```
nara_monitor/
  config.py    환경변수 설정
  api.py       나라장터 OpenAPI 호출 + 키워드 필터
  notifier.py  텔레그램 메시지 생성/전송
  state.py     중복 방지(이미 알린 공고 기록)
  main.py      엔트리포인트
.github/workflows/naramarket-monitor.yml   스케줄 실행
state/seen.json                            발송 기록(자동 커밋)
tests/                                     단위 테스트
```

## 문제 해결

- **알림이 안 와요**: Actions 탭의 실행 로그 확인. `resultCode=30`(SERVICE KEY ERROR) 이면 키 미승인/오타, `JSON 파싱 실패`면 엔드포인트(`G2B_API_BASE`) 확인.
- **너무 많이/적게 와요**: `SEARCH_KEYWORDS` 와 `LOOKBACK_HOURS` 조정.
- **API 트래픽 제한**: 공공데이터포털 개발계정은 일일 호출 한도가 있습니다. 호출이 많으면 `G2B_NUM_OF_ROWS` 를 키우고 주기를 늘리세요.
