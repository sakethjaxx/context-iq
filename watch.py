"""
Live dashboard — reads ~/.claude/context-iq-state.json every 2s and renders Rich UI.
Run in a separate terminal alongside Claude Code: python watch.py
"""
import sys
import json
import os
import time

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.live import Live
from rich.columns import Columns

STATE_FILE = os.path.expanduser("~/.claude/context-iq-state.json")
FILL = "█"
EMPTY = "░"

console = Console(highlight=False)


def _bar(filled: int, total: int, color: str) -> str:
    return f"[{color}]{FILL * filled}[/{color}]{EMPTY * (total - filled)}"


def build_display(state: dict) -> Columns:
    score = state.get("context_pressure_score", 100)
    raw_p = state.get("raw_pressure", 0)
    status = state.get("status", "fresh")
    turns = state.get("turns", 0)
    total_tokens = state.get("total_tokens", 0)
    live_ctx = state.get("live_context_tokens", 0)
    total_input = state.get("total_input_tokens", 0)
    total_output = state.get("total_output_tokens", 0)
    model = state.get("model", "unknown")
    confidence = state.get("confidence", "high")
    ctx_src = state.get("context_window_source", "known")

    color = {"fresh": "green", "warm": "yellow", "strained": "orange3", "critical": "red"}.get(status, "green")
    bar_width = 36

    score_bar = _bar(int(bar_width * score / 100), bar_width, color)
    pressure_bar = _bar(int(bar_width * raw_p / 100), bar_width, "red")

    meter = Text.from_markup(
        f"[bold]Context Pressure Score[/bold]\n"
        f"{score_bar} [{color}]{score:.0f}/100 {status.upper()}[/{color}]\n\n"
        f"[bold]Raw Pressure (this turn)[/bold]\n"
        f"{pressure_bar} {raw_p:.1f}%\n"
    )
    if confidence == "low":
        meter.append("\n[bold red]! Compaction detected — score may be optimistic[/bold red]")
    elif ctx_src == "defaulted":
        meter.append(f"\n[dim]Unknown model — window size defaulted[/dim]")

    meter_panel = Panel(meter, title="[bold]ContextIQ Live[/bold]", border_style=color)

    table = Table.grid(padding=(0, 2))
    table.add_column(style="dim")
    table.add_column()
    table.add_row("Model", model)
    table.add_row("Turns", str(turns))
    table.add_row("Input", f"{total_input:,}")
    table.add_row("Output", f"{total_output:,}")
    table.add_row("Total", f"{total_tokens:,}")
    table.add_row("Live ctx", f"{live_ctx:,}")
    stats_panel = Panel(table, title="Session Stats", border_style="blue")

    return Columns([meter_panel, stats_panel], equal=True)


def main():
    console.print("[dim]Watching context-iq state... Ctrl+C to quit[/dim]\n")
    last_turns = -1

    with Live(console=console, refresh_per_second=2, screen=False) as live:
        while True:
            try:
                if os.path.exists(STATE_FILE):
                    with open(STATE_FILE, encoding="utf-8") as f:
                        state = json.load(f)
                    live.update(build_display(state))
                    last_turns = state.get("turns", 0)
                else:
                    live.update(Panel("[dim]Waiting for first turn...[/dim]", title="ContextIQ Live", border_style="dim"))
            except Exception:
                pass
            time.sleep(2)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[dim]Stopped.[/dim]")
