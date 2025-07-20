"""Terminal utilities for better CLI output."""
import os
import sys

import art

from .system import initterm


class Colors:
    """ANSI color codes for terminal output."""
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

    @classmethod
    def disable(cls):
        """Disable colors (for non-tty output)."""
        cls.HEADER = ''
        cls.OKBLUE = ''
        cls.OKCYAN = ''
        cls.OKGREEN = ''
        cls.WARNING = ''
        cls.FAIL = ''
        cls.ENDC = ''
        cls.BOLD = ''
        cls.UNDERLINE = ''


# Disable colors if not a TTY
if not sys.stderr.isatty():
    Colors.disable()


def print_text(text: str = "", *args, **kwds):
    kwds.setdefault('file', sys.stderr)
    print(text, *args, **kwds)


def print_header(text: str, *args, **kwds):
    print_text(f"{Colors.BOLD}{Colors.HEADER}{text}{Colors.ENDC}", *args, **kwds)


def print_success(text: str, *args, **kwds):
    print_text(f"{Colors.OKGREEN}✓ {text}{Colors.ENDC}", *args, **kwds)


def print_error(text: str, *args, **kwds):
    print_text(f"{Colors.FAIL}✗ {text}{Colors.ENDC}", *args, **kwds)


def print_warning(text: str, *args, **kwds):
    print_text(f"{Colors.WARNING}⚠ {text}{Colors.ENDC}", *args, **kwds)


def print_info(text: str, *args, **kwds):
    print_text(f"{Colors.OKCYAN}ⓘ {text}{Colors.ENDC}", *args, **kwds)

def print_server_list(servers: dict):
    """Print a formatted list of servers."""
    if not servers:
        print_info("No servers configured")
        return

    print_header("Configured Servers")

    for name, server in servers.items():
        status_color = Colors.OKGREEN if server.enabled else Colors.WARNING
        status_text = "enabled" if server.enabled else "disabled"

        print_text(f"\n  {Colors.BOLD}{name}{Colors.ENDC} ({server.prefix}) - {status_color}{status_text}{Colors.ENDC}")
        print_text(f"    Source: {server.source}")

        if server.command:
            full_command = server.command
            if server.args:
                full_command += ' ' + ' '.join(server.args)
            print_text(f"    Command: {full_command}")

        if server.uri:
            print_text(f"    URI: {server.uri}")

        if server.cwd:
            print_text(f"    Working Dir: {server.cwd}")

        if server.env:
            print_text(f"    Environment: {', '.join(f'{k}={v}' for k, v in server.env.items())}")

        if server.notes:
            print_text(f"    Notes: {Colors.OKCYAN}{server.notes}{Colors.ENDC}")


def format_command(command: str, args: list[str] | None = None) -> str:
    """Format a command with arguments."""
    if args:
        return f"{command} {' '.join(args)}"
    return command


def print_status_summary(config_path: str, total: int, enabled: int, disabled: int):
    """Print a status summary."""
    print_header("Magg Status")
    print_text(f"""  Config: {config_path}
  Total servers: {Colors.BOLD}{total}{Colors.ENDC}
    {Colors.OKGREEN}● Enabled: {enabled}{Colors.ENDC}
    {Colors.WARNING}○ Disabled: {disabled}{Colors.ENDC}""")


def confirm_action(prompt: str) -> bool:
    """Ask for confirmation before an action."""
    try:
        response = input(f"{Colors.WARNING}{prompt} [y/N]: {Colors.ENDC}").strip().lower()
        return response in ('y', 'yes')
    except (EOFError, KeyboardInterrupt):
        print()  # New line after Ctrl+C
        return False


def print_startup_banner():
    """Print a beautiful startup banner.
    """
    # import pyfiglet
    # Use banner font which has solid # characters
    # ascii_art = pyfiglet.figlet_format("MAGG", font="big")
    # ascii_art = pyfiglet.figlet_format("MAGG", font="isometric3")
    # ascii_art = pyfiglet.figlet_format("MAGG", font="whimsy")

    # ascii_art = art.text2art("MAGG", font="cricket")
    # ascii_art = art.text2art("MAGG", font="diamond")
    # ascii_art = art.text2art("MAGG", font="tarty1")
    ascii_art = art.text2art("MAGG", font="isometric3")

    if os.environ.get("NO_RICH", "").lower() in ("1", "true", "yes"):
        print(ascii_art, file=sys.stderr)
    else:
        try:
            console = initterm()
            if console:
                # Apply gradient colors to each line
                lines = ascii_art.split('\n')
                colors = ['#4796E4', '#5B8FE6', '#7087E8', '#847ACE', '#9B72B8', '#B26BA2', '#C3677F']

                for i, line in enumerate(lines):
                    if line.strip():
                        color_idx = min(i, len(colors) - 1)
                        console.print(line, style=f"bold {colors[color_idx]}")

                console.print()
            else:
                print(ascii_art, file=sys.stderr)
        except ImportError:
            print(ascii_art, file=sys.stderr)
