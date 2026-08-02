# Magg and the Official MCP Registry

The [official MCP Registry](https://registry.modelcontextprotocol.io) is the
spec-blessed catalog of MCP servers, backed by `server.json` manifests and used as the
canonical discovery source by a growing number of MCP clients and subregistries.

Magg integrates with it in both directions.

## Searching the registry

`magg_search_servers` queries the official registry alongside Glama, GitHub, and npm.
Registry results are ranked highest because their entries carry structured install
metadata (packages, transports, environment variables) rather than free-form README
text, which also gives `magg_smart_configure` better raw material to work with.

```bash
mbro:magg> call magg_search_servers query="filesystem"
```

Each registry result includes the server's package identifiers (npm/pypi/oci), remote
endpoints, and version metadata under `metadata`.

## Publishing Magg to the registry

The repository root contains Magg's own registry manifest, [`server.json`](../server.json),
namespaced as `io.github.sitbon/magg` (validated against the official server schema).

To publish a release (requires GitHub authentication as the `sitbon` account or an org
member, since the `io.github.sitbon/*` namespace is verified via GitHub login):

```bash
# Install the publisher CLI (prebuilt binary; also available via brew on macOS)
curl -L "https://github.com/modelcontextprotocol/registry/releases/latest/download/mcp-publisher_linux_amd64.tar.gz" \
    | tar xz mcp-publisher
install -Dm755 mcp-publisher ~/.local/bin/mcp-publisher

# From the repo root
mcp-publisher login github
mcp-publisher publish
```

Note: building from source with `go install .../cmd/publisher@latest` produces a binary named
`publisher` (not `mcp-publisher`) in `$(go env GOPATH)/bin`, which is typically `~/go/bin` and
not on `PATH` by default — the prebuilt binary above is the simpler route.

**Release checklist**: the `version` fields in `server.json` (both the top-level version
and the pypi package version) must be bumped to match `pyproject.toml` before
publishing, and the PyPI release must already exist — the registry verifies that the
referenced package version is published.

**Ownership verification**: the registry proves control of the PyPI package by requiring
the line `mcp-name: io.github.sitbon/magg` in the package README as published on PyPI
(it fetches `https://pypi.org/pypi/magg/json` and checks the description). The marker
lives in `readme.md` (Appearances section) — do not remove it. Because PyPI descriptions
are immutable per release, a release published without the marker cannot be registered;
publish a new version instead.
