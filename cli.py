"""
VOIDLINK — CLI command handler.

Parses and dispatches commands typed at the terminal prompt.
All output goes through the logger module so colours are consistent.
"""

from __future__ import annotations

import sys
import time
import threading
from typing import TYPE_CHECKING, Callable

import logger
from config import PROMPT, DEFAULT_TTL
from utils import parse_addr, truncate, human_uptime, short_id

if TYPE_CHECKING:
    from node import VoidlinkNode


# ------------------------------------------------------------------ #
# Command registry                                                     #
# ------------------------------------------------------------------ #

Command = Callable[["CLIHandler", list[str]], None]
_COMMANDS: dict[str, Command] = {}
_HELP_TEXT: dict[str, str] = {}


def command(name: str, help_text: str = ""):
    """Decorator that registers a handler for a CLI command."""
    def decorator(fn: Command) -> Command:
        _COMMANDS[name] = fn
        _HELP_TEXT[name] = help_text
        return fn
    return decorator


class CLIHandler:
    """
    Wraps a VoidlinkNode and exposes all /command handlers.

    The public interface is `run()`, which blocks on stdin until
    the user types /quit.
    """

    def __init__(self, node: "VoidlinkNode") -> None:
        self._node = node
        self._running = True

    # ------------------------------------------------------------------ #
    # Main loop                                                            #
    # ------------------------------------------------------------------ #

    def run(self) -> None:
        """Block on stdin; dispatch commands."""
        import sys
        interactive = sys.stdin.isatty()
        while self._running:
            try:
                if interactive:
                    raw = input(PROMPT).strip()
                else:
                    # Non-interactive (piped / scripted): read without prompt
                    line = sys.stdin.readline()
                    if not line:
                        # EOF on non-interactive stdin — keep the node alive
                        # so it can still serve peers; just pause the loop.
                        import time
                        time.sleep(0.1)
                        continue
                    raw = line.strip()
            except (EOFError, KeyboardInterrupt):
                self._cmd_quit([])
                break

            if not raw:
                continue

            if raw.startswith("/"):
                self._dispatch(raw[1:])
            else:
                logger.cmd(
                    "Commands start with '/'. Type /help for a list.",
                    self._node.node_id,
                )

    def _dispatch(self, raw: str) -> None:
        parts = raw.split(maxsplit=1)
        name = parts[0].lower()
        args = parts[1].split() if len(parts) > 1 else []

        handler = _COMMANDS.get(name)
        if handler is None:
            logger.error(
                f"Unknown command: /{name}. Type /help for a list.",
                self._node.node_id,
            )
            return

        try:
            handler(self, args)
        except Exception as exc:
            logger.error(f"Command /{name} error: {exc}", self._node.node_id)

    # ------------------------------------------------------------------ #
    # Commands                                                             #
    # ------------------------------------------------------------------ #

    @command("help", "Show this help message")
    def _cmd_help(self, args: list[str]) -> None:
        lines = [
            "",
            "  VOIDLINK — available commands",
            "  " + "─" * 40,
        ]
        for name, text in sorted(_HELP_TEXT.items()):
            lines.append(f"  /{name:<16} {text}")
        lines.append("")
        for line in lines:
            logger.cmd(line, self._node.node_id)

    @command("send", "/send <message> [--ttl <seconds>]  — Broadcast a message")
    def _cmd_send(self, args: list[str]) -> None:
        if not args:
            logger.error("Usage: /send <message text> [--ttl <seconds>]", self._node.node_id)
            return

        # Optional --ttl flag
        ttl = DEFAULT_TTL
        text_parts: list[str] = []
        i = 0
        while i < len(args):
            if args[i] == "--ttl" and i + 1 < len(args):
                try:
                    ttl = int(args[i + 1])
                    i += 2
                    continue
                except ValueError:
                    logger.error("TTL must be an integer.", self._node.node_id)
                    return
            text_parts.append(args[i])
            i += 1

        content = " ".join(text_parts)
        if not content:
            logger.error("Message content cannot be empty.", self._node.node_id)
            return

        msg = self._node.send_message(content, ttl=ttl)
        logger.send(
            f"Sent message {msg.short_id()} to {len(self._node.network.get_peers())} peer(s)  "
            f"| ttl={ttl}s | \"{truncate(content)}\"",
            self._node.node_id,
        )

    @command("connect", "/connect <host:port>  — Connect to a peer node")
    def _cmd_connect(self, args: list[str]) -> None:
        if not args:
            logger.error("Usage: /connect <host:port>", self._node.node_id)
            return
        try:
            host, port = parse_addr(args[0])
        except ValueError as exc:
            logger.error(str(exc), self._node.node_id)
            return

        logger.info(f"Connecting to {host}:{port}…", self._node.node_id)
        ok, result = self._node.network.connect_to(host, port)
        if ok:
            logger.peer(f"Connected to Node {result} at {host}:{port}", self._node.node_id)
        else:
            logger.error(result, self._node.node_id)

    @command("disconnect", "/disconnect <host:port>  — Disconnect from a peer")
    def _cmd_disconnect(self, args: list[str]) -> None:
        if not args:
            logger.error("Usage: /disconnect <host:port>", self._node.node_id)
            return
        try:
            host, port = parse_addr(args[0])
        except ValueError as exc:
            logger.error(str(exc), self._node.node_id)
            return

        ok, result = self._node.network.disconnect_from(host, port)
        if ok:
            logger.peer(f"Disconnected from Node {result} ({host}:{port})", self._node.node_id)
        else:
            logger.error(result, self._node.node_id)

    @command("peers", "List all connected peers")
    def _cmd_peers(self, args: list[str]) -> None:
        peers = self._node.network.get_peers()
        if not peers:
            logger.cmd("No peers connected.", self._node.node_id)
            return
        logger.cmd(f"Connected peers ({len(peers)}):", self._node.node_id)
        for p in peers:
            logger.cmd(f"  • {p.node_id:<10} {p.address}", self._node.node_id)

    @command("messages", "List all messages currently in memory")
    def _cmd_messages(self, args: list[str]) -> None:
        msgs = self._node.network.get_messages()
        if not msgs:
            logger.cmd("No messages in memory.", self._node.node_id)
            return
        logger.cmd(f"In-memory messages ({len(msgs)}):", self._node.node_id)
        for m in sorted(msgs, key=lambda x: x.timestamp):
            rem = max(0.0, m.seconds_remaining())
            logger.cmd(
                f"  [{m.short_id()}] from={m.sender_id} hops={m.hop_count} "
                f"ttl={rem:.1f}s  \"{truncate(m.content, 50)}\"",
                self._node.node_id,
            )

    @command("node", "Show this node's info")
    def _cmd_node(self, args: list[str]) -> None:
        n = self._node
        logger.cmd(
            f"Node ID: {n.node_id}  |  Listening: {n.network._advertised_host()}:{n.network.port}",
            n.node_id,
        )

    @command("stats", "Show runtime statistics")
    def _cmd_stats(self, args: list[str]) -> None:
        n = self._node
        nw = n.network
        rt = n.routing
        tm = n.ttl_manager

        uptime = human_uptime(time.time() - n.started_at)
        peers = nw.get_peers()
        msgs = nw.get_messages()

        import psutil, os
        try:
            proc = psutil.Process(os.getpid())
            mem_mb = proc.memory_info().rss / 1024 / 1024
            mem_str = f"{mem_mb:.1f} MB"
        except Exception:
            mem_str = "N/A"

        sim_latency = f"{nw.latency_ms} ms" if nw.latency_ms > 0 else "off"
        sim_loss    = f"{nw.packet_loss_pct:.0f}%" if nw.packet_loss_pct > 0 else "off"

        rows = [
            ("Node ID",            n.node_id),
            ("Listen address",     f"{nw._advertised_host()}:{nw.port}"),
            ("Connected peers",    str(len(peers))),
            ("Messages in memory", str(len(msgs))),
            ("Messages sent",      str(n.messages_sent_count)),
            ("Messages received",  str(rt.messages_received)),
            ("Messages forwarded", str(rt.messages_forwarded)),
            ("Messages expired",   str(tm.messages_expired)),
            ("Uptime",             uptime),
            ("Memory usage",       mem_str),
            ("Sim latency",        sim_latency),
            ("Sim packet loss",    sim_loss),
        ]

        logger.stat("── Node Statistics ─────────────────────", n.node_id)
        for label, value in rows:
            logger.stat(f"  {label:<22} {value}", n.node_id)
        logger.stat("────────────────────────────────────────", n.node_id)

    @command("clear", "Clear the terminal screen")
    def _cmd_clear(self, args: list[str]) -> None:
        import os
        os.system("clear" if os.name != "nt" else "cls")

    @command("quit", "Shut down this node")
    def _cmd_quit(self, args: list[str]) -> None:
        logger.info("Shutting down node…", self._node.node_id)
        self._running = False
        self._node.shutdown()
        sys.exit(0)


# Bind command methods to the CLIHandler class using the decorator registry
for _name, _fn in _COMMANDS.items():
    setattr(CLIHandler, f"_cmd_{_name}", _fn)
