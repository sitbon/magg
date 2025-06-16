# MAGG Test Suite

## Test Organization

The test suite is organized into focused test modules:

### Core Functionality Tests
- `test_transport.py` - Tests for transport selection utilities (✅ All passing)
- `test_integration.py` - Integration tests for source/server creation (✅ All passing)
- `test_server_add.py` - Unit tests for server add functionality
- `test_config.py` - Configuration model tests
- `test_basic.py` - Basic MAGG functionality tests

### Specialized Tests
- `test_mounting.py` - FastMCP mounting tests
- `test_tool_delegation.py` - Tool delegation and discovery tests
- `test_error_handling.py` - Error handling scenarios
- `test_client_api.py` - FastMCP client API tests
- `test_config_migration.py` - Configuration migration tests
- `test_fastmcp_integration.py` - FastMCP integration exploration

## Running Tests

Run all tests:
```bash
python -m pytest magg/test/
```

Run specific test modules:
```bash
# Transport selection tests
python -m pytest magg/test/test_transport.py -v

# Integration tests
python -m pytest magg/test/test_integration.py -v
```

## Test Status

### ✅ Fully Passing
- Transport selection (`test_transport.py`) - 13 tests
- Basic integration (`test_integration.py`) - 3 tests

### ⚠️ Needs Updates
Many older tests need updates due to API changes:
- MCPSource now requires name as primary identifier
- MCPServer uses `source_name` instead of `source_url`
- Config structure changed significantly

## Key Test Patterns

### Testing MCP Tools
MCP tools are wrapped as FunctionTool objects. To test them:

```python
from magg import server as magg_server_module

# Get the tool
tool = getattr(magg_server_module, 'magg_add_source')

# Call the underlying function
if hasattr(tool, 'fn'):
    result = await tool.fn(name="test")
```

### Mocking Patterns
- Mock `pathlib.Path.mkdir` for directory creation
- Mock `magg.discovery.metadata.SourceMetadataCollector` for metadata
- Mock `magg.utils.validate_working_directory` for validation logic