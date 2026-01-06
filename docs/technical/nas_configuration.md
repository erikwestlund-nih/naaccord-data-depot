# NAS Configuration for File Storage

## Environment Variables

The NA-ACCORD system uses environment variables to configure NAS mount points for production deployments. This ensures all file operations use the proper network-attached storage instead of local disk.

### Required Environment Variables

#### `NAS_WORKSPACE_PATH`
- **Purpose**: Base path for all temporary workspace files during processing
- **Example**: `/mnt/nas/naaccord` or `/mnt/nas/depot-workspace`
- **Used by**: 
  - `WorkspaceManager` - Creates `{NAS_WORKSPACE_PATH}/workspace/` for temporary processing
  - `PHIStorageManager` - Creates `{NAS_WORKSPACE_PATH}/phi_workspace/` for PHI data
- **Development**: If not set, uses local `storage/workspace/` directory

#### `NAS_STORAGE_PATH` (if needed for permanent storage)
- **Purpose**: Base path for permanent file storage (reports, submissions, etc.)
- **Example**: `/mnt/nas/naaccord-data` or `/mnt/nas/depot-storage`
- **Used by**: `StorageManager` for permanent file storage
- **Development**: If not set, uses local `storage/` directory

### Directory Structure on NAS

When `NAS_WORKSPACE_PATH=/mnt/nas/naaccord`, the system creates:

```
/mnt/nas/naaccord/
├── workspace/                    # Temporary processing files
│   ├── upload_prechecks/        # Upload precheck working directories
│   │   └── {upload_id}/         # Per-upload temporary files
│   │       ├── input.csv
│   │       ├── data.duckdb
│   │       └── notebook_compile/
│   ├── submissions/             # Full submission processing
│   │   └── {submission_id}/     # Per-submission temporary files
│   └── cleanup_logs/            # Audit trail of cleanup operations
└── phi_workspace/               # PHI data temporary workspace
    └── temp_{id}_{type}.duckdb  # Temporary DuckDB files
```

### Docker Configuration

For Docker deployments, mount the NAS and set environment variables:

```yaml
# docker-compose.yml
services:
  web:
    environment:
      - NAS_WORKSPACE_PATH=/mnt/nas/naaccord
      - NAS_STORAGE_PATH=/mnt/nas/naaccord-data
    volumes:
      - /mnt/nas/naaccord:/mnt/nas/naaccord
      - /mnt/nas/naaccord-data:/mnt/nas/naaccord-data
```

### Kubernetes Configuration

For Kubernetes deployments:

```yaml
# deployment.yaml
spec:
  containers:
  - name: naaccord
    env:
    - name: NAS_WORKSPACE_PATH
      value: "/mnt/nas/naaccord"
    - name: NAS_STORAGE_PATH
      value: "/mnt/nas/naaccord-data"
    volumeMounts:
    - name: nas-workspace
      mountPath: /mnt/nas/naaccord
    - name: nas-storage
      mountPath: /mnt/nas/naaccord-data
  volumes:
  - name: nas-workspace
    nfs:
      server: nas.example.com
      path: /export/naaccord
  - name: nas-storage
    nfs:
      server: nas.example.com
      path: /export/naaccord-data
```

### Local Development

For local development, you can either:

1. **Use local directories** (default):
   - Don't set any NAS environment variables
   - System uses `storage/workspace/` for temporary files
   - System uses `storage/` for permanent files

2. **Simulate NAS locally**:
   ```bash
   export NAS_WORKSPACE_PATH=/tmp/nas-simulation
   export NAS_STORAGE_PATH=/tmp/nas-storage
   ```

3. **Mount actual NAS for testing**:
   ```bash
   # Mount NAS locally
   sudo mount -t nfs nas.example.com:/export/naaccord /mnt/nas
   export NAS_WORKSPACE_PATH=/mnt/nas/naaccord
   ```

### Permissions Requirements

The application needs the following permissions on NAS directories:

- **Read/Write/Execute** on workspace directories
- **Create/Delete** files and directories
- **Recommended ownership**: Application service account
- **Recommended permissions**: `755` for directories, `644` for files

### Testing NAS Configuration

Test that NAS is properly configured:

```bash
# Test workspace manager with NAS
export NAS_WORKSPACE_PATH=/mnt/nas/naaccord
python manage.py shell -c "
from depot.storage.workspace_manager import WorkspaceManager
w = WorkspaceManager()
print('Workspace root:', w.workspace_root)
print('Can write:', w.workspace_root.exists() and os.access(w.workspace_root, os.W_OK))
"

# Test cleanup with NAS
python manage.py cleanup_workspace --show-usage
```

### Monitoring and Alerts

When using NAS, monitor:

1. **Available space**: Alert if NAS has < 10GB free
2. **Write performance**: Alert if write operations take > 5 seconds
3. **Mount status**: Alert if NAS becomes unmounted
4. **Cleanup failures**: Alert if files can't be deleted from NAS

### Troubleshooting

Common NAS issues and solutions:

1. **Permission Denied**:
   - Check NAS mount permissions
   - Verify service account has write access
   - Check directory ownership

2. **NAS Not Mounted**:
   - Check `mount` command output
   - Verify network connectivity to NAS
   - Check NFS service status

3. **Slow Performance**:
   - Check network bandwidth
   - Verify NAS isn't full (< 90% capacity)
   - Consider using SSD-backed NAS for workspace

4. **Cleanup Failures**:
   - Check file locks on NAS
   - Verify no processes holding files open
   - Check NAS-level snapshots or backups