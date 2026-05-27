import sys
import os
from dotenv import load_dotenv
from rich.prompt import Prompt
from chat import ChatSession
from display import print_response, print_stats, print_warning, console

load_dotenv()

COMMANDS = {
    "/stats":  "Show session stats and intelligence meter",
    "/reset":  "Reset session (clear history + token counts)",
    "/model":  "Show current model",
    "/help":   "Show this help",
    "/quit":   "Exit",
}


def print_help():
    console.print("\n[bold]Commands:[/bold]")
    for cmd, desc in COMMANDS.items():
        console.print(f"  [cyan]{cmd}[/cyan]  {desc}")
    console.print()


def main():
    if not os.getenv("ANTHROPIC_API_KEY"):
        console.print("[red]Error: ANTHROPIC_API_KEY not set. Copy .env.example → .env and add key.[/red]")
        sys.exit(1)

    model = sys.argv[1] if len(sys.argv) > 1 else "claude-sonnet-4-6"
    session = ChatSession(model=model)

    console.print(f"\n[bold green]Chat Token Usage[/bold green]  model: [cyan]{model}[/cyan]")
    console.print("Type [cyan]/help[/cyan] for commands.\n")

    while True:
        try:
            user_input = Prompt.ask("[bold blue]You[/bold blue]").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Goodbye.[/dim]")
            break

        if not user_input:
            continue

        if user_input == "/quit":
            break
        elif user_input == "/help":
            print_help()
        elif user_input == "/stats":
            print_stats(session.stats)
        elif user_input == "/reset":
            session.reset()
            console.print("[yellow]Session reset.[/yellow]")
        elif user_input == "/model":
            console.print(f"Model: [cyan]{session.model}[/cyan]")
        elif user_input.startswith("/"):
            console.print(f"[red]Unknown command: {user_input}[/red]")
        else:
            with console.status("[dim]Thinking...[/dim]"):
                response = session.send(user_input)
            print_response(response)
            print_stats(session.stats)
            print_warning(session.stats)


if __name__ == "__main__":
    main()
