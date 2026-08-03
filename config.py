"""
VOIDLINK — Configuration defaults and constants.
"""

APP_NAME: str = "VOIDLINK"
VERSION: str = "2.0.0"

# Network defaults
DEFAULT_HOST: str = "0.0.0.0"
DEFAULT_PORT: int = 5000
REQUEST_TIMEOUT: int = 5       # seconds for outbound HTTP calls

# Message defaults
DEFAULT_TTL: int = 300          # 5 minutes (was 10 s — more useful for chat)
MAX_HOPS: int = 20              # hard cap to prevent infinite loops
MESSAGE_CHECK_INTERVAL: float = 1.0   # how often TTL janitor runs (seconds)

# CLI
PROMPT: str = "voidlink> "
BANNER: str = r"""
 __   ___  ___ ____  _     ___ _   _ _  __
 \ \ / / |/ _ \_ _|| |   |_ _| \ | | |/ /
  \ V /| | | | || | | |    | ||  \| | ' /
   \_/ |_|\___/|___||_|   |___|_|\__|_|\_\
"""

# ── Performance ───────────────────────────────────────────────────────────────
BROADCAST_WORKERS: int = 16     # ThreadPoolExecutor workers for concurrent sends
RETRY_ATTEMPTS: int = 3         # outbound send retries before dropping peer
RETRY_BACKOFF: float = 0.3      # base seconds; doubles each attempt (exponential)
CONNECTION_POOL_SIZE: int = 20  # max keep-alive connections per host

# ── Security ──────────────────────────────────────────────────────────────────
CRYPTO_ENABLED: bool = True     # AES-256-GCM + Ed25519; set False for debug only
