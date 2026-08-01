# Magg and the Stateless MCP Spec (2026-07-28)

The [MCP 2026-07-28 specification](https://blog.modelcontextprotocol.io/posts/2026-07-28/)
moves the Model Context Protocol from a bidirectional, stateful protocol to a **stateless
request/response model**. This page explains what changed, how it affects Magg, and what the
migration path looks like.

## What changed in the spec

- **Stateless protocol core**: Sessions and the `initialize`/`initialized` handshake are gone,
  along with the `Mcp-Session-Id` header. Every request is self-describing — it carries its own
  protocol version, client identity, and capabilities in `_meta` — so any request can land on any
  server instance behind a plain load balancer.
- **Multi Round-Trip Requests (MRTR)**: Server-initiated requests (`sampling/createMessage`,
  `elicitation/create`, `roots/list`) that previously required an open stream are replaced by a
  request/retry pattern: the server returns `resultType: "input_required"` and the client retries
  with answers in `inputResponses`.
- **Cacheable list results**: `tools/list`, `prompts/list`, `resources/list`, and
  `resources/read` responses can carry `ttlMs` and `cacheScope` so clients can cache instead of
  re-fetching.
- **Header-based routing**: Method and tool names travel in `Mcp-Method` and `Mcp-Name` HTTP
  headers, so gateways and rate limiters can route without parsing JSON bodies.
- **Unified subscriptions**: A `subscriptions/listen` stream replaces the previous notification
  endpoints for clients that still want push updates.
- **Deprecations**: Roots, Sampling, Logging, and the legacy HTTP+SSE transport are deprecated
  with a twelve-month minimum migration window.
- **Authorization hardening**: RFC 9207 issuer validation is required, and Dynamic Client
  Registration is deprecated in favor of Client ID Metadata Documents (CIMD).

## Why this makes an aggregator *more* useful

Statelessness is great for serverless deployment, but something still has to own the messy parts:
long-lived stdio subprocesses, backend connection lifecycles, change detection, and caching. That
is exactly the layer Magg occupies:

- **Session anchor**: Magg can hold persistent connections to backends (stdio subprocesses,
  legacy SSE servers, session-oriented HTTP servers) while presenting a clean, stateless-ready
  front to clients. Old-world backends keep working behind a new-world front door.
- **Cache authority**: Magg already maintains the merged tool list across all mounted backends
  and knows precisely when it changes (mount, unmount, reload, backend notification). That makes
  it the natural place to serve cacheable `tools/list` results with honest `ttlMs` values —
  invalidating exactly when a backend changes rather than on a timer.
- **Notification bridge**: Backends that push `tool_list_changed` notifications feed Magg's
  message coordinator today. In a stateless world, Magg can translate those into cache
  invalidation and a single `subscriptions/listen` stream for clients that want it.
- **Hierarchical aggregation**: Because Magg is both an MCP server and an MCP client, Magg
  instances can be layered — a top-level Magg aggregating per-team or per-project Maggs. A
  stateless front end makes the top layer horizontally scalable while lower layers keep
  the stateful backend connections local to where they run.

## Impact inventory

Where Magg currently relies on stateful protocol features:

### As a server (facing Magg's clients)

| Feature | Where | Spec status |
|---|---|---|
| LLM sampling (`ctx.sample`) | `magg_smart_configure`, `magg_analyze_servers` (`magg/server/server.py`) | Sampling deprecated → migrate to MRTR |
| Push notifications to clients | `ServerMessageCoordinator` (`magg/messaging.py`) | Replaced by `subscriptions/listen` |
| Logging notifications | `magg/messaging.py` | Logging utility deprecated |
| Streamable HTTP sessions | FastMCP `run_http_async` (`magg/server/manager.py`) | Session layer removed from core |

### As a client (facing backend servers)

| Feature | Where | Spec status |
|---|---|---|
| Backend notification handlers | `BackendMessageHandler` (`magg/proxy/server.py`) | Backends move to `subscriptions/listen` / ttlMs caching |
| Legacy HTTP+SSE transport | `magg/util/transport.py` (URIs ending in `/sse`) | Deprecated, 12-month window |
| Persistent backend sessions | `ServerManager` mounts (`magg/server/manager.py`) | Still fine — this is the value Magg adds |

### Authentication

Magg's bearer auth is self-issued JWT with a local RSA keypair — it does not use OAuth Dynamic
Client Registration, so the DCR→CIMD transition does not affect existing setups. Issuer
validation already compares `iss` against the configured value.

## Migration plan

Magg tracks the official SDKs: statelessness arrives for Magg primarily through FastMCP and the
MCP Python SDK. The plan, roughly in order:

1. **SDK upgrades**: Adopt FastMCP / `mcp` releases that implement 2026-07-28 (stateless
   transport, MRTR, `subscriptions/listen`). Magg's transport and session plumbing is delegated
   to the SDK, so most of the surface migrates with the dependency.
2. **Dual-stack compatibility**: Keep supporting pre-2026 backends (sessions, SSE,
   notifications) as a client indefinitely — aggregating old servers behind a new front is a core
   use case, not a legacy burden.
3. **MRTR for sampling tools**: Rework `magg_smart_configure` and `magg_analyze_servers` to use
   MRTR-style `input_required` results when client sampling is unavailable, with the existing
   no-sampling fallback retained.
4. **Cacheable aggregated lists**: Emit `ttlMs`/`cacheScope` on aggregated `tools/list` results,
   invalidated by mount/unmount/reload events.
5. **Notification translation**: Map backend `*_list_changed` notifications to cache
   invalidation + `subscriptions/listen` for clients that opt in.
6. **Header-based routing passthrough**: Preserve `Mcp-Method`/`Mcp-Name` headers when proxying,
   so infrastructure between client → Magg → backend can route and authorize consistently.

Progress is tracked in [GitHub issues](https://github.com/sitbon/magg/issues).
