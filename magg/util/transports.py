"""Custom transport classes that don't validate script paths.

These transports pass through script arguments without validation,
letting the underlying command fail if the script doesn't exist.
"""
from fastmcp.client import PythonStdioTransport, StdioTransport, NodeStdioTransport

__all__ = "NoValidatePythonStdioTransport", "NoValidateNodeStdioTransport"


class NoValidatePythonStdioTransport(PythonStdioTransport):
    """Python transport that doesn't validate script paths."""

    def __init__(
        self,
        script_path: str,
        args: list[str] | None = None,
        python_cmd: str = "python",
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        keep_alive: bool = True
    ):
        """Initialize without script validation.

        Args:
            script_path: Script path or module argument (e.g., "-m", "script.py")
            args: Additional arguments
            python_cmd: Python command to use
            env: Environment variables
            cwd: Working directory
            keep_alive: Whether to keep process alive
        """
        # Build the full command without validation
        full_args = [script_path] if script_path else []
        if args:
            full_args.extend(args)

        # Initialize parent StdioTransport directly to skip PythonStdioTransport's validation
        StdioTransport.__init__(
            self,
            command=python_cmd,
            args=full_args,
            env=env,
            cwd=cwd,
            keep_alive=keep_alive
        )


class NoValidateNodeStdioTransport(NodeStdioTransport):
    """Node.js transport that doesn't validate script paths."""

    def __init__(
        self,
        script_path: str,
        args: list[str] | None = None,
        node_cmd: str = "node",
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        keep_alive: bool = True
    ):
        """Initialize without script validation.

        Args:
            script_path: Script path or other node argument
            args: Additional arguments
            node_cmd: Node command to use
            env: Environment variables
            cwd: Working directory
            keep_alive: Whether to keep process alive
        """
        # Build the full command without validation
        full_args = [script_path] if script_path else []
        if args:
            full_args.extend(args)

        # Initialize parent StdioTransport directly to skip NodeStdioTransport's validation
        StdioTransport.__init__(
            self,
            command=node_cmd,
            args=full_args,
            env=env,
            cwd=cwd,
            keep_alive=keep_alive
        )
