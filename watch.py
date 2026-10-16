"""
Live dashboard for a Claude Code session. Needs `rich` (pip install rich).
Run in a second terminal alongside Claude Code:

    python watch.py                  # most recently active session
    python watch.py --session ID     # a specific session
"""
import argparse
import sys
import time

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from rich.columns import Columns
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

import claude_code as cc
from meter import RECOMMENDATIONS, STATUS_COLORS

FILL = "█"
EMPTY = "░"

console = Console(highlight=False)


def _bar(fraction: float, width: int, color: str) -> str:
    filled = max(0, min(width, int(width * fraction)))
    return f"[{color}]{FILL * filled}[/{color}]{EMPTY * (width - filled)}"


def current_snapshot(session_id: str = None):
    if session_id:
        return cc.resolve_snapshot(session_id)
    state = cc.latest_state()
    return cc.resolve_snapshot(state["session_id"], cwd=state.get("cwd")) if state else None


def build_display(snap: cc.Snapshot):
    if snap is None or not snap.has_usage:
        note = "Conversation compacted; waiting for the next reply..." if snap else "Waiting for the first reply..."
        return Panel(f"[dim]{note}[/dim]", title="ContextIQ Live", border_style="dim")

    color = STATUS_COLORS[snap.status]
    width = 36
    meter = Text.from_markup(
        f"[bold]Intelligence Score[/bold]\n"
        f"{_bar(snap.score / 100, width, color)} [{color}]{snap.score:.0f}/100 {snap.status.upper()}[/{color}]\n\n"
        f"[bold]Context Pressure[/bold] [dim](vs {cc.fmt_tokens(snap.scored_window)} horizon)[/dim]\n"
        f"{_bar(snap.pressure, width, 'red')} {100 * snap.pressure:.1f}%\n\n"
        f"[bold]Window Used[/bold]\n"
        f"{_bar(snap.window_pct / 100, width, 'blue')} {snap.window_pct:.1f}% of {cc.fmt_tokens(snap.window)}\n\n"
        f"[dim]{RECOMMENDATIONS[snap.status]}[/dim]"
    )
    meter_panel = Panel(meter, title="[bold]ContextIQ Live[/bold]", border_style=color)

    table = Table.grid(padding=(0, 2))
    table.add_column(style="dim")
    table.add_column()
    table.add_row("Model", snap.model_name or snap.model or "unknown")
    table.add_row("Session", snap.session_id[:8])
    table.add_row("Project", snap.project_dir or snap.cwd)
    table.add_row("In context", f"{snap.used_tokens:,}")
    table.add_row("Last reply", f"{snap.output_tokens:,} out")
    table.add_row("Window", f"{snap.window:,} ({snap.window_source})")
    stats_panel = Panel(table, title="Session", border_style="blue")

    return Columns([meter_panel, stats_panel], equal=True)


def main():
    parser = argparse.ArgumentParser(description="Live ContextIQ dashboard")
    parser.add_argument("--session", help="Claude Code session id (default: most recently active)")
    parser.add_argument("--interval", type=float, default=2.0, help="refresh seconds")
    args = parser.parse_args()

    console.print("[dim]Watching Claude Code context... Ctrl+C to quit[/dim]\n")
    with Live(console=console, refresh_per_second=2, screen=False) as live:
        while True:
            try:
                live.update(build_display(current_snapshot(args.session)))
            except Exception:
                pass
            time.sleep(args.interval)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[dim]Stopped.[/dim]")
