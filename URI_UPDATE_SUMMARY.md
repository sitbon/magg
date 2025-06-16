# URI Update Summary

## Changes Made

### 1. **magg/server.py**
- Updated `magg_add_source` function:
  - Changed parameter from `url` to `uri` (optional)
  - Added logic: if name is provided but no uri, creates a file:// URI pointing to `.magg/sources/<name>`
  - Updated all references from `source.url` to `source.uri`
  - Updated all references from `source_url` to `source_uri` throughout the file
  
- Updated all other functions to use `source_uri` instead of `source_url`:
  - `magg_add_server`
  - `magg_remove_source` 
  - `magg_list_servers`
  - `magg_search_sources`
  - `get_source_metadata`
  - `configure_server_prompt`
  - `analyze_source_setup_prompt`
  - `magg_generate_server_config`
  - `magg_smart_configure`

### 2. **magg/cli/__main__.py**
- Updated `cmd_add_source` to match server.py logic for file:// URI creation
- Updated all references from `args.url` to `args.uri`
- Updated all references from `args.source_url` to `args.source_uri`
- Updated argument parser to use `uri` instead of `url`
- Updated help text and examples to use "URI" terminology

### 3. **magg/core/config.py**
- Already uses `uri` field in `MCPSource` dataclass
- Already uses `source_uri` field in `MCPServer` dataclass

## API Changes

### Old API:
```python
magg_add_source(url="https://github.com/example/repo", name="example")
magg_add_server(source_url="https://github.com/example/repo", ...)
```

### New API:
```python
# With explicit URI
magg_add_source(uri="https://github.com/example/repo", name="example")

# With just name (creates file:// URI)
magg_add_source(name="local-source")  # Creates file:///path/to/.magg/sources/local-source

magg_add_server(source_uri="https://github.com/example/repo", ...)
```

## CLI Changes

### Old CLI:
```bash
magg add-source <url> <name>
magg add-server <name> <source_url> ...
```

### New CLI:
```bash
magg add-source <uri> <name>
magg add-source <name>  # Creates file:// URI
magg add-server <name> <source_uri> ...
```

## Notes
- Test files still use `source_url` but these don't affect the runtime API
- Internal methods in discovery/metadata.py still use `url` parameters but this is fine as they're internal
- The change maintains backward compatibility in the sense that URIs are a superset of URLs