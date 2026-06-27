"""Custom transport classes that don't validate script paths.

These transports pass through script arguments without validation,
letting the underlying command fail if the script doesn't exist.
"""
from fastmcp.client import PythonStdioTransport, StdioTransport, NodeStdioTransport, NpxStdioTransport

__all__ = "NoValidatePythonStdioTransport", "NoValidateNodeStdioTransport", "NoValidateNpxStdioTransport"


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
        full_args = [script_path] if script_path else []
        if args:
            full_args.extend(args)

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
        full_args = [script_path] if script_path else []
        if args:
            full_args.extend(args)

        StdioTransport.__init__(
            self,
            command=node_cmd,
            args=full_args,
            env=env,
            cwd=cwd,
            keep_alive=keep_alive
        )


class NoValidateNpxStdioTransport(NpxStdioTransport):
    """NPX transport that doesn't validate npx availability at construction.

    FastMCP's NpxStdioTransport raises if `npx` is not on PATH when constructed.
    Magg defers that failure to connection time, matching its python/node transports.
    """

    def __init__(
        self,
        package: str,
        args: list[str] | None = None,
        project_directory: str | None = None,
        env_vars: dict[str, str] | None = None,
        use_package_lock: bool = True,
        keep_alive: bool = True
    ):
        """Initialize without validating npx presence.

        Args:
            package: Name of the npm package to run
            args: Arguments to pass to the package command
            project_directory: Working directory
            env_vars: Environment variables
            use_package_lock: Whether to add --prefer-offline
            keep_alive: Whether to keep process alive
        """
        npx_args = ["--prefer-offline"] if use_package_lock else []
        npx_args.append(package)
        if args:
            npx_args.extend(args)

        StdioTransport.__init__(
            self,
            command="npx",
            args=npx_args,
            env=env_vars,
            cwd=project_directory,
            keep_alive=keep_alive
        )
        self.package = package
