# GitHub Actions Workflows for Magg

This directory contains GitHub Actions workflows for automated testing, publishing, and Docker image management for the Magg package.

## Workflows

### 1. Test (`test.yml`)
- **Trigger**: On every push and pull request to any branch
- **Purpose**: Run pytest across multiple Python versions
- **Actions**:
  - Read Python version from `.python-version`
  - Test on Python 3.12, 3.13, and the project's default version
  - Install all dependencies via uv
  - Run pytest with all tests

### 2. Publish to PyPI (`publish.yml`)
- **Trigger**: On push to main branch
- **Purpose**: Automatically publish new versions to PyPI without version commits
- **Actions**:
  1. Run all tests (must pass to continue)
  2. Calculate version as X.Y.Z.C (C = commit count)
  3. Update version in pyproject.toml temporarily
  4. Build the package
  5. Create GPG-signed tag (magg/vX.Y.Z.C)
  6. Push tag to repository
  7. Create GitHub release with changelog
  8. Publish to PyPI

### 3. Docker Build and Publish (`docker-publish.yml`)
- **Trigger**: 
  - Push to beta branch
  - Version tags matching `magg/v*`
  - Pull requests to main or beta (build only)
- **Purpose**: Build and publish multi-stage Docker images
- **Actions**:
  1. Build and test dev image with multiple Python versions
  2. Run pytest inside dev container
  3. If tests pass, build pro and pre images
  4. Push all images to GitHub Container Registry (ghcr.io)
- **Images Created**:
  - `pro` (production): WARNING log level
  - `pre` (staging): INFO log level  
  - `dev` (development): DEBUG log level, includes dev dependencies

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

This ensures every commit to main gets a unique, incrementing version number without requiring version bump commits.

## Docker Image Tags

Docker images are tagged based on the trigger:
- **From beta branch**: `beta`, `beta-pre`, `beta-dev`
- **From version tags**: `1.2.3.4`, `1.2`, `latest` (main only)
- **With Python versions**: `beta-dev-py3.12`, `beta-dev-py3.13`, etc.

## Environment Configuration

The publish environment requires:
- `SIGNED_COMMIT_USER`: Git user name for commits
- `SIGNED_COMMIT_EMAIL`: Git user email for commits

## Usage

1. **Regular Development**: Push to any branch to run tests
2. **Publishing to PyPI**: Merge to main branch to automatically publish
3. **Docker Images**: 
   - Push to beta branch for testing images
   - Version tags on main create production images
4. **Testing Publishing**: Use the manual workflow dispatch to dry-run

## Branch Strategy

- **main**: Production branch - triggers PyPI releases and Docker builds on tags
- **beta**: Testing branch - triggers Docker builds on every push
- **feature branches**: Run tests only

## Troubleshooting

- If GPG signing fails, ensure the GPG key is properly imported and the secrets are correct
- If PyPI publishing fails, check that the PYPI_TOKEN has sufficient permissions
- If Docker builds fail, check that dev image tests are passing
- Container tests use the dev image to gate all other image builds