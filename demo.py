"""
Demo script - renders GOOD / BAD / UGLY states for screenshots.
No API calls. No cost.
"""
import sys
import io
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from meter import SessionStats
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

console = Console(highlight=False, file=sys.stdout)

FILL = "█"
EMPTY = "░"


def _bar(filled: int, total: int, color: str) -> str:
    return f"[{color}]{FILL * filled}[/{color}]{EMPTY * (total - filled)}"


def render_meter(s: SessionStats) -> Panel:
    score = s.intelligence_score
    pressure = s.context_pressure
    color = s.status_color
    bar_width = 40
    score_bar = _bar(int(bar_width * score / 100), bar_width, color)
    pressure_bar = _bar(int(bar_width * pressure), bar_width, "red")
    content = Text.from_markup(
        f"[bold]Intelligence Score[/bold]\n"
        f"{score_bar} [{color}]{score:.0f}/100 {s.status.upper()}[/{color}]\n\n"
        f"[bold]Context Pressure[/bold]\n"
        f"{pressure_bar} {pressure * 100:.1f}% of {s.context_window // 1000}k window\n"
        f"[dim]{s.usable_window - s.live_context_tokens:,} tokens remaining[/dim]"
    )
    return Panel(content, title="Intelligence Meter", border_style=color)


def render_stats(s: SessionStats) -> Panel:
    from rich.table import Table
    table = Table.grid(padding=(0, 2))
    table.add_column(style="dim")
    table.add_column()
    table.add_row("Model", s.model)
    table.add_row("Turns", str(s.turns))
    table.add_row("Input tokens", f"{s.total_input_tokens:,}")
    table.add_row("Output tokens", f"{s.total_output_tokens:,}")
    table.add_row("Total tokens", f"{s.total_tokens:,}")
    table.add_row("Live context", f"{s.live_context_tokens:,}")
    return Panel(table, title="Session Stats", border_style="blue")


def show(label, input_tokens, output_tokens, turns, warning=None):
    s = SessionStats(model="claude-sonnet-4-6")
    s.total_input_tokens = input_tokens
    s.total_output_tokens = output_tokens
    s.live_context_tokens = input_tokens
    s.turns = turns
    console.rule(f"[bold] {label} | IQ: {s.intelligence_score:.0f}/100 | {s.status.upper()} ")
    console.print(render_stats(s))
    console.print(render_meter(s))
    if warning:
        console.print(f"[bold {s.status_color}]{warning}[/bold {s.status_color}]")
    console.print()


show("GOOD",  input_tokens=5_000,   output_tokens=1_200,  turns=3)
show("BAD",   input_tokens=149_000, output_tokens=22_000, turns=12,
     warning="! Session strained - consider /reset soon.")
show("UGLY",  input_tokens=183_000, output_tokens=28_000, turns=28,
     warning="!! CRITICAL context pressure - reset strongly recommended.")
