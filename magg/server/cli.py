"""Small CLI to run the MAGG server directly, e.g. `python -m magg.server`
"""
import argparse
import asyncio


def main():
    """Run the MAGG server."""
    parser = create_parser()
    args = parser.parse_args()

    from ..cli import cmd_serve

    asyncio.run(cmd_serve(args))


def create_parser():
    """Create the command line argument parser."""
    parser = argparse.ArgumentParser(description="Run the MAGG server.")
    from ..cli import __version__, cmd_serve_args
    parser.add_argument(
        "-V", "--version",
        action="version",
        version=f"%(prog)s {__version__}",
        help="Show the version of the MAGG server."
    )
    parser.add_argument(
        '--config',
        type=str,
        help='Path to config file (default: .magg/config.json in current directory)'
    )
    parser.add_argument("-q", "--quiet", action="store_true", help="Output as little as possible")
    cmd_serve_args(parser)
    return parser


if __name__ == "__main__":
    main()
