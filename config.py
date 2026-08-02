"""
VOIDLINK — Configuration defaults and constants.
"""

APP_NAME: str = "VOIDLINK"
VERSION: str = "1.0.0"

# Network defaults
DEFAULT_HOST: str = "0.0.0.0"
DEFAULT_PORT: int = 5000
REQUEST_TIMEOUT: int = 3  # seconds for outbound HTTP calls

# Message defaults
DEFAULT_TTL: int = 10       # seconds before a message expires
MAX_HOPS: int = 20          # hard cap to prevent infinite loops
MESSAGE_CHECK_INTERVAL: float = 1.0  # how often TTL janitor runs (seconds)

# CLI
PROMPT: str = "voidlink> "
BANNER: str = r"""
 __   ___  ___ ____  _     ___ _   _ _  __
 \ \ / / |/ _ \_ _|| |   |_ _| \ | | |/ /
  \ V /| | | | || | | |    | ||  \| | ' /
   \_/ |_|\___/|___||_|   |___|_|\__|_|\_\
"""
