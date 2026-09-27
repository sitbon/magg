# Security Policy

## Supported Versions

Security fixes go into the latest release only. Older versions aren't patched, so upgrade to get fixes.

## What Magg Allows by Design

Magg exists to let an MCP client add, configure and run other MCP servers. Adding a server means running a command, so anyone who can call Magg's tools can run commands as the user Magg runs as. Treat access to a Magg server like shell access.

These are not vulnerabilities:

- Running commands through `magg_add_server` or other Magg tools, by any client that can reach the server.
- Running an HTTP server without authentication. `magg serve --http` listens on localhost unless you pass `--host`. If you make it reachable from elsewhere, for example with `--host` or by publishing the Docker image's port, enable authentication first with `magg auth init`.
- Clients reading server configuration, including `env` values and headers, through Magg's tools and resources.
- Anything a backend MCP server does once it's added. It runs with the same permissions as Magg.

## In Scope

Please report issues like these:

- Getting past bearer authentication when it's enabled, or flaws in token validation.
- Changing configuration or running commands in read-only mode (`MAGG_READ_ONLY`).
- Private keys, tokens or other secrets exposed to someone without access to Magg, for example through file permissions or logs.
- Anything that lets someone who can't reach Magg's tools run commands anyway.

## Reporting a Vulnerability

Report privately through GitHub's private vulnerability reporting: open the repository's Security tab and choose "Report a vulnerability". Please don't open a public issue or pull request for an unfixed vulnerability.

Include the Magg version, how Magg was started (stdio, HTTP, hybrid or Docker), and steps to reproduce.

Magg is maintained on a best-effort basis and has no bug bounty. Reports about the by-design behavior above will be closed.
