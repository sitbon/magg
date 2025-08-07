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
- **Purpose**: Automatically publish new versions to PyPI when version changes
- **Actions**:
  1. Check if version in pyproject.toml has changed since last publish
  2. If changed, build the package
  3. Create GPG-signed tag (vX.Y.Z)
  4. Create simplified tag for major.minor (vX.Y)
  5. Push tags to repository
  6. Create GitHub release with changelog
  7. Publish to PyPI
  8. Update latest-publish tag for future comparisons

### 3. Docker Build and Publish (`docker-publish.yml`)
- **Trigger**: 
  - Push to main or beta branch
  - Version tags matching `v*.*.*`
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

- `PAT_TOKEN`: Personal Access Token with read/write permissions on Content
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

The version number follows the pattern `X.Y.Z` where:
- X = Major version (breaking changes)
- Y = Minor version (new features)
- Z = Patch version (bug fixes)

The workflow only publishes when the version in pyproject.toml is manually changed.

## Docker Image Tags

Docker images are tagged based on the trigger:
- **From beta branch**: `beta`, `beta-pre`, `beta-dev`
- **From version tags**: `1.2.3`, `1.2`, `latest` (main only)
- **With Python versions**: `beta-dev-py3.12`, `beta-dev-py3.13`, etc.

## Environment Configuration

The publish environment requires:
- `SIGNED_COMMIT_USER`: Git username for commits
- `SIGNED_COMMIT_EMAIL`: Git user email for commits

## Usage

**Publishing to PyPI**: 
1. Update version in pyproject.toml
2. Commit and push to main branch
3. Workflow will automatically detect version change and publish

**Docker Images**: 
- Push to beta branch for testing images
- Version tags created by publish workflow trigger production images

**Testing Publishing**: Use the manual workflow dispatch to dry-run

## Branch Strategy

- **main**: Production branch - triggers PyPI releases and Docker builds on tags
- **beta**: Testing branch - triggers Docker builds on every push
- **feature branches**: Run tests only

## Troubleshooting

- If git operations fail, ensure the PAT_TOKEN has sufficient permissions
- If GPG signing fails, ensure the GPG key is properly imported and the secrets are correct
- If PyPI publishing fails, check that the PYPI_TOKEN has sufficient permissions
- If Docker builds fail, check that dev image tests are passing
- Container tests use the dev image to gate all other image builds