"""
Demo script - renders GOOD / BAD / UGLY meter states for screenshots.
No API calls. No cost. Needs `rich`.
"""
from display import console, print_stats, print_warning
from meter import SessionStats


def show(label, live_tokens, output_tokens, turns):
    s = SessionStats(model="claude-haiku-4-5")  # 200k window
    s.total_input_tokens = live_tokens * turns // 2
    s.total_output_tokens = output_tokens
    s.live_context_tokens = live_tokens
    s.turns = turns
    console.rule(f"[bold] {label} | IQ: {s.context_pressure_score:.0f}/100 | {s.status.upper()} ")
    print_stats(s)
    print_warning(s)
    console.print()


show("GOOD", live_tokens=6_200, output_tokens=1_200, turns=3)
show("BAD", live_tokens=165_000, output_tokens=22_000, turns=12)
show("UGLY", live_tokens=184_000, output_tokens=28_000, turns=28)
