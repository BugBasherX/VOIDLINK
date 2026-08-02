"""
VOIDLINK — Colored terminal logger.

Tags:
  [INFO]  General information
  [RECV]  Message received from a peer
  [FWD]   Message forwarded to peers
  [SEND]  Message sent by this node
  [TTL]   Message expired / TTL event
  [PEER]  Peer connect / disconnect
  [ERROR] Error or warning
  [CMD]   Command feedback
"""

import threading
from datetime import datetime
from typing import Optional

# ANSI color codes
RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"

BLACK   = "\033[30m"
RED     = "\033[31m"
GREEN   = "\033[32m"
YELLOW  = "\033[33m"
BLUE    = "\033[34m"
MAGENTA = "\033[35m"
CYAN    = "\033[36m"
WHITE   = "\033[37m"

BRIGHT_RED    = "\033[91m"
BRIGHT_GREEN  = "\033[92m"
BRIGHT_YELLOW = "\033[93m"
BRIGHT_BLUE   = "\033[94m"
BRIGHT_MAGENTA = "\033[95m"
BRIGHT_CYAN   = "\033[96m"
BRIGHT_WHITE  = "\033[97m"

# Tag → (label_color, message_color)
_TAG_STYLES: dict[str, tuple[str, str]] = {
    "INFO":  (BRIGHT_CYAN,    WHITE),
    "RECV":  (BRIGHT_GREEN,   BRIGHT_WHITE),
    "FWD":   (BRIGHT_MAGENTA, WHITE),
    "SEND":  (BRIGHT_BLUE,    BRIGHT_WHITE),
    "TTL":   (BRIGHT_YELLOW,  YELLOW),
    "PEER":  (CYAN,           WHITE),
    "ERROR": (BRIGHT_RED,     RED),
    "CMD":   (BRIGHT_WHITE,   WHITE),
    "STAT":  (GREEN,          WHITE),
}

_print_lock = threading.Lock()


def _timestamp() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _log(tag: str, message: str, node_id: Optional[str] = None) -> None:
    label_color, msg_color = _TAG_STYLES.get(tag, (WHITE, WHITE))
    ts = DIM + _timestamp() + RESET
    tag_str = f"{BOLD}{label_color}[{tag:5}]{RESET}"
    node_str = f" {DIM}({node_id}){RESET}" if node_id else ""
    line = f"{ts} {tag_str}{node_str} {msg_color}{message}{RESET}"
    with _print_lock:
        print(f"\r{line}\n", end="", flush=True)


def info(message: str, node_id: Optional[str] = None) -> None:
    _log("INFO", message, node_id)


def recv(message: str, node_id: Optional[str] = None) -> None:
    _log("RECV", message, node_id)


def fwd(message: str, node_id: Optional[str] = None) -> None:
    _log("FWD", message, node_id)


def send(message: str, node_id: Optional[str] = None) -> None:
    _log("SEND", message, node_id)


def ttl(message: str, node_id: Optional[str] = None) -> None:
    _log("TTL", message, node_id)


def peer(message: str, node_id: Optional[str] = None) -> None:
    _log("PEER", message, node_id)


def error(message: str, node_id: Optional[str] = None) -> None:
    _log("ERROR", message, node_id)


def cmd(message: str, node_id: Optional[str] = None) -> None:
    _log("CMD", message, node_id)


def stat(message: str, node_id: Optional[str] = None) -> None:
    _log("STAT", message, node_id)


def banner(text: str) -> None:
    """Print a raw colored banner line."""
    with _print_lock:
        print(f"{BRIGHT_CYAN}{BOLD}{text}{RESET}", flush=True)
