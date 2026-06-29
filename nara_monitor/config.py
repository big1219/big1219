"""환경변수 기반 설정.

모든 비밀값(서비스키, 텔레그램 토큰 등)은 환경변수 / GitHub Actions Secrets 로
주입한다. 코드나 저장소에 직접 적지 않는다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


# 기본 검색 키워드(엔진오일 + 윤활유 등 확장). SEARCH_KEYWORDS 환경변수로 덮어쓸 수 있다.
DEFAULT_KEYWORDS = [
    "엔진오일",
    "엔진 오일",
    "엔진오일류",
    "구매",
    "윤활유",
    "윤활제",
    "부동액",
    "유압유",
    "기어",
    "트랙터유",
    "디젤",
    "가솔린",
    "루브리컨트",
    "엔진윤활유",
    "engine oil",
    "lubricant",
]

# 기본 조회 대상 operation. 물품(Thng)을 기본으로 한다.
# 용역/공사까지 보려면 G2B_OPERATIONS 에 콤마로 나열한다.
#   예) getBidPblancListInfoThng,getBidPblancListInfoServc
DEFAULT_OPERATIONS = ["getBidPblancListInfoThng"]

# 나라장터 입찰공고정보서비스(공공데이터포털 데이터ID 15129394)의 기본 base URL.
# 발급 화면의 "엔드포인트"가 다르면 G2B_API_BASE 로 덮어쓴다.
DEFAULT_API_BASE = "https://apis.data.go.kr/1230000/ad/BidPublicInfoService"


def _split(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass
class Config:
    service_key: str
    telegram_bot_token: str
    telegram_chat_id: str
    api_base: str = DEFAULT_API_BASE
    operations: list[str] = field(default_factory=lambda: list(DEFAULT_OPERATIONS))
    keywords: list[str] = field(default_factory=lambda: list(DEFAULT_KEYWORDS))
    lookback_hours: int = 48
    num_of_rows: int = 500
    max_pages: int = 40
    state_file: str = "state/seen.json"
    request_timeout: int = 30
    # True 면 새 공고를 텔레그램으로 보내지 않고 콘솔에만 출력(테스트용).
    dry_run: bool = False

    @classmethod
    def from_env(cls) -> "Config":
        missing = [
            name
            for name in ("G2B_SERVICE_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")
            if not os.environ.get(name)
        ]
        if missing:
            raise SystemExit(
                "필수 환경변수가 없습니다: "
                + ", ".join(missing)
                + "\n(.env.example 와 README 의 설정 안내를 참고하세요.)"
            )

        keywords_env = os.environ.get("SEARCH_KEYWORDS")
        operations_env = os.environ.get("G2B_OPERATIONS")

        return cls(
            service_key=os.environ["G2B_SERVICE_KEY"],
            telegram_bot_token=os.environ["TELEGRAM_BOT_TOKEN"],
            telegram_chat_id=os.environ["TELEGRAM_CHAT_ID"],
            api_base=os.environ.get("G2B_API_BASE", DEFAULT_API_BASE).rstrip("/"),
            operations=_split(operations_env) if operations_env else list(DEFAULT_OPERATIONS),
            keywords=_split(keywords_env) if keywords_env else list(DEFAULT_KEYWORDS),
            lookback_hours=int(os.environ.get("LOOKBACK_HOURS", "48")),
            num_of_rows=int(os.environ.get("G2B_NUM_OF_ROWS", "500")),
            max_pages=int(os.environ.get("G2B_MAX_PAGES", "40")),
            state_file=os.environ.get("STATE_FILE", "state/seen.json"),
            request_timeout=int(os.environ.get("REQUEST_TIMEOUT", "30")),
            dry_run=os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes"),
        )
