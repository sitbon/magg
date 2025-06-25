# Magg Authentication Guide

This guide covers how to set up and use bearer token authentication in Magg.

## Overview

Magg uses RSA keypair-based bearer token authentication with JWT tokens. When enabled, all clients must provide a valid JWT token to access the server. Authentication is optional - if no keys exist, the server runs without authentication.

## Quick Start

### 1. Initialize Authentication

Generate RSA keypair (one-time setup):
```bash
magg auth init
```

This creates:
- Private key: `~/.ssh/magg/magg.key`
- Public key: `~/.ssh/magg/magg.key.pub`

### 2. Generate JWT Token

```bash
# Display token on screen
magg auth token

# Export to environment variable
export MAGG_JWT=$(magg auth token -q)
```

### 3. Connect with Authentication

Using MaggClient (recommended):
```python
from magg.client import MaggClient

# Automatically uses MAGG_JWT environment variable
async with MaggClient("http://localhost:8000/mcp") as client:
    tools = await client.list_tools()
```

## Detailed Setup

### Custom Configuration

Initialize with custom parameters:
```bash
# Custom audience and issuer
magg auth init --audience myapp --issuer https://mycompany.com

# Custom key location
magg auth init --key-path /opt/magg/keys
```

### Token Generation Options

Generate tokens with specific parameters:
```bash
# Custom subject and expiration
magg auth token --subject "my-service" --hours 168

# Include scopes (informational only, not enforced)
magg auth token --scopes "read" "write" "admin"

# Export format for shell scripts
magg auth token --export
# Output: export MAGG_JWT="eyJ..."
```

### Key Management

Display keys for backup or verification:
```bash
# Show public key (safe to share)
magg auth public-key

# Show private key (keep secret!)
magg auth private-key

# Export private key in single-line format for env vars
magg auth private-key --oneline
```

## Environment Variables

### Server Configuration

- `MAGG_PRIVATE_KEY`: Private key content (takes precedence over file)
  ```bash
  export MAGG_PRIVATE_KEY="-----BEGIN RSA PRIVATE KEY-----\nMIIE..."
  ```

### Client Configuration

- `MAGG_JWT`: JWT token for client authentication
  ```bash
  export MAGG_JWT="eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9..."
  ```

## Configuration Files

### Auth Configuration (`.magg/auth.json`)

```json
{
  "bearer": {
    "issuer": "https://magg.local",
    "audience": "myapp",
    "key_path": "/custom/path/to/keys"
  }
}
```

### Key File Locations

Default locations:
- Private key: `{key_path}/{audience}.key`
- Public key: `{key_path}/{audience}.key.pub`

Example with custom audience "prod":
- `/home/user/.ssh/magg/prod.key`
- `/home/user/.ssh/magg/prod.key.pub`

## Client Examples

### Python with MaggClient

```python
import os
from magg.client import MaggClient

# Method 1: Auto-load from environment
os.environ['MAGG_JWT'] = 'your-jwt-token'
async with MaggClient("http://localhost:8000/mcp") as client:
    tools = await client.list_tools()

# Method 2: Explicit token
from fastmcp.client import BearerAuth
auth = BearerAuth('your-jwt-token')
async with MaggClient("http://localhost:8000/mcp", auth=auth) as client:
    tools = await client.list_tools()

# Method 3: Transparent proxy mode (no prefixes)
async with MaggClient("http://localhost:8000/mcp", transparent=True) as client:
    # Call tools without prefixes
    result = await client.call_tool("add", {"a": 5, "b": 3})
    # Instead of: client.call_tool("calc_add", {"a": 5, "b": 3})
```

### Using with curl

```bash
# Get JWT token
JWT=$(magg auth token -q)

# Make authenticated request
curl -H "Authorization: Bearer $JWT" http://localhost:8000/mcp/
```

## Disabling Authentication

To run Magg without authentication:

### Option 1: Don't Generate Keys
Simply don't run `magg auth init`. No keys = no auth.

### Option 2: Remove Existing Keys
```bash
rm ~/.ssh/magg/magg.key*
```

### Option 3: Configure Non-Existent Path
Edit `.magg/auth.json`:
```json
{
  "bearer": {
    "key_path": "/path/that/does/not/exist"
  }
}
```

## Security Best Practices

1. **Protect Private Keys**
   - Files are created with 0600 permissions (owner read/write only)
   - Never commit private keys to version control
   - Use `.gitignore` to exclude `.magg/` directory

2. **Token Management**
   - Use short expiration times for development (default: 24 hours)
   - Longer expiration for production services
   - Rotate tokens regularly

3. **Production Deployment**
   - Use environment variables for keys and tokens
   - Consider using a secrets management service
   - Enable HTTPS for transport security

4. **Multiple Environments**
   - Use different audiences for dev/staging/prod
   - Separate key pairs per environment
   - Example: `magg auth init --audience prod`

## Troubleshooting

### Check Authentication Status
```bash
magg auth status
```

Output shows:
- Current configuration
- Key file locations
- Whether keys exist

### Common Issues

1. **"Authentication is not enabled"**
   - No private key found
   - Run `magg auth init` or check `MAGG_PRIVATE_KEY`

2. **"Invalid token"**
   - Token expired (check with jwt.io)
   - Wrong audience or issuer
   - Using token from different key pair

3. **"Permission denied" when reading key**
   - Check file permissions: `ls -la ~/.ssh/magg/`
   - Should be 0600 for private key

## Advanced Usage

### Custom Token Claims

While Magg doesn't enforce scopes, you can include them for client-side logic:
```bash
magg auth token --scopes "projects:read" "servers:write"
```

### Token Introspection

Decode a token to see its claims:
```bash
# Using Python
python -c "import jwt; print(jwt.decode('$MAGG_JWT', options={'verify_signature': False}))"
```

### Integration with CI/CD

Generate long-lived tokens for automated systems:
```bash
# 30-day token for CI
magg auth token --subject "github-actions" --hours 720 --quiet
```