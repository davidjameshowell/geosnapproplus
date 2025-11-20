# Frontend Permission Fix for Kubernetes

## Problem
The frontend container was experiencing permission errors when trying to write to `/app/media`:
```
PermissionError: [Errno 13] Permission denied: '/app/media/50dc277a79924b03b7e601ea6c954fcd.png'
```

## Root Cause
The Kubernetes deployment runs the frontend container as user ID 1000 (non-root) for security, but the Docker image was creating the `/app/media` directory as root, causing permission conflicts with the mounted PersistentVolume.

## Solution Applied

### 1. Dockerfile Changes
Updated `/frontend/Dockerfile` to:
- Create a non-root user (`appuser`) with UID/GID 1000
- Create the `/app/media` directory with proper ownership
- Run the application as the non-root user

Key changes:
```dockerfile
# Create non-root user and media directory with proper permissions
RUN groupadd -r appuser -g 1000 && \
    useradd -r -u 1000 -g appuser appuser && \
    mkdir -p /app/media && \
    chown -R appuser:appuser /app

# Switch to non-root user
USER appuser
```

### 2. App.py Improvements
Enhanced error handling and logging in `/frontend/app.py` to:
- Test write permissions on startup
- Provide detailed error messages if permission issues occur
- Log the current user ID and directory permissions for debugging

## Steps to Deploy the Fix

### 1. Rebuild the Docker Image
```bash
cd /home/david/repos/geosnappro-thefinal/frontend
docker build -t frontend:latest .
```

### 2. If using a registry, push the image
```bash
# Tag and push to your registry
docker tag frontend:latest your-registry/frontend:latest
docker push your-registry/frontend:latest
```

### 3. Redeploy to Kubernetes
```bash
# Delete the existing pods to force recreation with new image
kubectl delete pod -l app.kubernetes.io/name=frontend -n <your-namespace>

# Or perform a rolling restart
kubectl rollout restart deployment/frontend -n <your-namespace>
```

### 4. Verify the Fix
```bash
# Check pod logs for successful initialization
kubectl logs -l app.kubernetes.io/name=frontend -n <your-namespace> --tail=50

# You should see:
# "Media directory initialized successfully at /app/media"
```

## Verification
After deployment, the frontend should:
1. Successfully create the `/app/media` directory
2. Write screenshot files without permission errors
3. Log "Media directory initialized successfully" on startup

## Additional Notes
- The Helm chart already has `fsGroup: 1000` in the podSecurityContext, which ensures the mounted volume is accessible by the user
- The PersistentVolumeClaim settings remain unchanged
- No changes are needed to the Kubernetes YAML files themselves

