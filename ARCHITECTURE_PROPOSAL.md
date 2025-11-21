# Architecture Restructuring Proposal

## Overview
This document proposes a restructuring of the GeoSnappro codebase to improve organization, clarity, and maintainability. The current structure has some legacy components and inconsistent naming that can be confusing for new developers.

## Current Issues
1.  **Unused Code**: The `backend-api` directory appears to be a legacy component that is no longer used. The `frontend` now communicates directly with `screenshot-api`.
2.  **Inconsistent Naming**: `gluetun-k8s` and `gluetun-api-docker` perform similar functions for different environments but have inconsistent naming.
3.  **Root Directory Clutter**: The root directory contains a mix of source code folders, configuration files, and scripts.

## Proposed Structure

```
/
├── services/                   # Source code for all microservices
│   ├── frontend/               # The web UI application
│   ├── screenshot-api/         # Core screenshot and recording service
│   ├── gluetun-api-k8s/        # VPN manager for Kubernetes (was gluetun-k8s)
│   └── gluetun-api-docker/     # VPN manager for Docker Compose (was gluetun-api-docker)
├── deploy/                     # Deployment configurations
│   ├── charts/                 # Helm charts
│   └── k8s/                    # Raw Kubernetes manifests (if any)
├── tests/                      # End-to-end tests
├── docs/                       # Documentation
├── scripts/                    # Helper scripts (e.g., port_forward_frontend.sh)
├── docker-compose.yml          # Local development configuration
└── README.md
```

## Detailed Changes

### 1. Create `services/` Directory
Move all active application components into a dedicated `services/` directory.
- Move `frontend/` -> `services/frontend/`
- Move `screenshot-api/` -> `services/screenshot-api/`
- Move `gluetun-k8s/` -> `services/gluetun-api-k8s/`
- Move `gluetun-api-docker/` -> `services/gluetun-api-docker/`

### 2. Remove Legacy Code
- **Delete `backend-api/`**: This directory is unused. The `frontend` is configured to talk to `screenshot-api` (via `BACKEND_URL` env var) in both Docker Compose and Kubernetes environments.

### 3. Organize Scripts
- Move `port_forward_frontend.sh` to `scripts/`.

### 4. Update References
- Update `docker-compose.yml` build contexts.
- Update `tests/run_kind_e2e.sh` build paths.
- Update `charts/geosnappro/values.yaml` if it references local paths (unlikely for Helm, but good to check).
- Update GitHub Actions workflows (if any).

## Benefits
- **Clarity**: It is immediately obvious which folders contain source code (`services/`) vs infrastructure (`deploy/`).
- **Cleanliness**: The root directory is decluttered.
- **Maintainability**: Removing dead code (`backend-api`) reduces confusion.
- **Consistency**: Grouping related services together makes the architecture easier to understand.

## Implementation Plan
1.  Create new directories (`services`, `deploy`).
2.  Move directories to their new locations.
3.  Delete `backend-api`.
4.  Update `docker-compose.yml` paths.
5.  Update `tests/run_kind_e2e.sh` paths.
6.  Verify local development with `docker-compose up`.
7.  Verify E2E tests with `tests/run_kind_e2e.sh`.
