import sys
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from meter import SessionStats

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

console = Console(highlight=False)


def render_stats_panel(stats: SessionStats) -> Panel:
    table = Table.grid(padding=(0, 2))
    table.add_column(style="dim")
    table.add_column()
    table.add_row("Model", stats.model)
    table.add_row("Turns", str(stats.turns))
    table.add_row("Input tokens", f"{stats.total_input_tokens:,}")
    table.add_row("Output tokens", f"{stats.total_output_tokens:,}")
    table.add_row("Total tokens", f"{stats.total_tokens:,}")
    if stats.cache_read_tokens:
        table.add_row("Cache read", f"{stats.cache_read_tokens:,}")
    if stats.cache_creation_tokens:
        table.add_row("Cache write", f"{stats.cache_creation_tokens:,}")
    return Panel(table, title="Session Stats", border_style="blue")


def render_meter_panel(stats: SessionStats) -> Panel:
    score = stats.context_pressure_score
    pressure = stats.context_pressure
    color = stats.status_color
    status = stats.status.upper()
    bar_width = 40

    filled = int(bar_width * (score / 100))
    score_bar = f"[{color}]{'█' * filled}[/{color}]{'░' * (bar_width - filled)}"

    p_filled = int(bar_width * pressure)
    pressure_bar = f"[red]{'█' * p_filled}[/red]{'░' * (bar_width - p_filled)}"

    content = Text.from_markup(
        f"[bold]Intelligence Score[/bold]\n"
        f"{score_bar} [{color}]{score:.0f}/100 {status}[/{color}]\n\n"
        f"[bold]Context Pressure[/bold]\n"
        f"{pressure_bar} {pressure * 100:.1f}% of {stats.context_window // 1000}k window\n"
        f"[dim]{stats.usable_window - stats.live_context_tokens:,} tokens remaining[/dim]"
    )
    return Panel(content, title="Intelligence Meter", border_style=color)


def print_response(text: str):
    console.print(Panel(text, title="Assistant", border_style="green"))


def print_stats(stats: SessionStats):
    console.print(render_stats_panel(stats))
    console.print(render_meter_panel(stats))


def print_warning(stats: SessionStats):
    msg = {
        "strained": "[bold orange3]! Session strained - consider /reset soon.[/bold orange3]",
        "critical": "[bold red]!! CRITICAL context pressure - reset strongly recommended.[/bold red]",
    }.get(stats.status)
    if msg:
        console.print(msg)
