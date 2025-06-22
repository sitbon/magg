# GitHub Actions Workflows for MAGG

This directory contains GitHub Actions workflows for automated testing and publishing of the MAGG package.

## Workflows

### 1. Test (`test.yml`)
- **Trigger**: On every push and pull request to any branch
- **Purpose**: Run pytest to ensure all tests pass
- **Actions**:
  - Install Python 3.13 via uv
  - Install all dependencies
  - Run pytest

### 2. Publish to PyPI (`publish.yml`)
- **Trigger**: On push to main branch
- **Purpose**: Automatically publish new versions to PyPI with GPG-signed commits
- **Actions**:
  1. Run all tests (must pass to continue)
  2. Update version number to include commit count
  3. Build the package
  4. Create GPG-signed commit with version and SHA512 hash
  5. Create GPG-signed tag (magg/vX.Y.Z.C)
  6. Publish to PyPI
  7. Push commit and tag back to main branch
  8. Create GitHub release

### 3. Branch Protection (`branch-protection.yml`)
- **Trigger**: On pull requests to main branch
- **Purpose**: Ensure tests pass before allowing merge to main
- **Actions**:
  - Run full test suite
  - Code quality checks (placeholder for future linting)

### 4. Manual Publish Dry Run (`manual-publish.yml`)
- **Trigger**: Manual workflow dispatch
- **Purpose**: Test the publishing process without actually publishing
- **Actions**:
  - Simulates the entire publish workflow
  - Shows what would be committed and tagged
  - Does not actually publish or push changes

## Required Secrets

The following secrets must be configured in the GitHub repository settings:

- `GPG_PRIVATE_KEY`: The GPG private key for signing commits and tags
- `GPG_PASSPHRASE`: The passphrase for the GPG key
- `PYPI_TOKEN`: The API token for publishing to PyPI

## Required Environment Variables

The following environment variables should be set in the `publish` environment:

- `GPG_PUBLIC_KEY`: The GPG public key (informational)
- `PYPI_TOKEN_NAME`: The name of the PyPI token (informational)
- `SIGNED_COMMIT_USER`: The name for git commits
- `SIGNED_COMMIT_EMAIL`: The email for git commits

## Version Numbering

The version number follows the pattern `X.Y.Z.C` where:
- X.Y.Z is the base version from pyproject.toml
- C is the commit count from git history

This ensures every commit to main gets a unique, incrementing version number.

## Commit Message Format

Published commits have the format:
```
X.Y.Z.C <previous-commit-sha>
<sha512-hash-of-package> dist/magg-X.Y.Z.C.tar.gz
```

This provides a verifiable chain of commits and package integrity.

## Usage

1. **Regular Development**: Push to any branch to run tests
2. **Publishing**: Merge to main branch to automatically publish
3. **Testing Publishing**: Use the manual workflow dispatch to dry-run the process
4. **Branch Protection**: Configure main branch to require the branch-protection check

## Troubleshooting

- If GPG signing fails, ensure the GPG key is properly imported and the secrets are correct
- If PyPI publishing fails, check that the PYPI_TOKEN has sufficient permissions
- If tests fail on main, the publish job will not run