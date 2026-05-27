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
    provider_name = os.getenv("PROVIDER", "groq").lower()
    key_map = {"groq": "GROQ_API_KEY", "claude": "ANTHROPIC_API_KEY"}
    required_key = key_map.get(provider_name)
    if required_key and not os.getenv(required_key):
        console.print(f"[red]Error: {required_key} not set for provider '{provider_name}'. Copy .env.example → .env and add key.[/red]")
        sys.exit(1)

    session = ChatSession()
    model = session.provider.model_id

    console.print(f"\n[bold green]ContextIQ[/bold green]  model: [cyan]{model}[/cyan]")
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
            console.print(f"Model: [cyan]{session.provider.model_id}[/cyan]")
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
