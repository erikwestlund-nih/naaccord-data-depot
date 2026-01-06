# Development Streaming Setup

## Overview

NA-ACCORD uses a two-server architecture where the web server never stores files locally, instead streaming all uploads to a secure services server. This document explains how to set up and use the streaming architecture in development.

## Architecture

### Production Architecture
```
Internet → Web Server (Port 80/443) → Services Server (Internal)
           (No file storage)          (File storage + processing)
```

### Development Architecture
```
Browser → Web Server (Port 8000) → Services Server (Port 8001)
          (No file storage)         (File storage + processing)
```

## Development Setup

### Prerequisites

1. **Docker Services Running**
   ```bash
   dockerna start
   ```
   This starts: MariaDB, Redis, MinIO, Flower

2. **Environment Ready**
   - Python virtual environment activated
   - All dependencies installed

### Starting Development Servers

Use the enhanced tmux script:

```bash
tmna  # or /Users/erikwestlund/code/projects/tmux/start_naaccord.sh
```

This creates a tmux session with these windows:

| Window | Purpose | Port | Environment |
|--------|---------|------|-------------|
| `django` | Web Server | 8000 | `SERVER_ROLE=web` |
| `services` | Services Server | 8001 | `SERVER_ROLE=services` |
| `celery` | Background Tasks | - | - |
| `npm` | Frontend Assets | - | - |
| Other windows... | Shells, R, Docker logs | - | - |

### Environment Variables

Both servers use these environment variables:

```bash
# Common
DJANGO_SETTINGS_MODULE=depot.settings
INTERNAL_API_KEY=dev-streaming-key-123

# Web Server (Port 8000)
SERVER_ROLE=web

# Services Server (Port 8001)  
SERVER_ROLE=services
```

## How File Streaming Works

### Upload Flow

1. **User uploads file** via web interface (`localhost:8000`)
2. **Web server receives file** but doesn't save it locally
3. **Web server streams file** to services server (`localhost:8001`) via internal API
4. **Services server saves file** to `storage/workspace/`
5. **Services server processes file** (DuckDB conversion, R analysis, etc.)
6. **Web server returns response** to user

### Storage Behavior

| Component | Web Server | Services Server |
|-----------|------------|-----------------|
| **Storage Driver** | `RemoteStorageDriver` | `LocalFileSystemStorage` |
| **File Storage** | None (streams only) | `storage/workspace/` |
| **API Endpoints** | Calls services server | Handles file operations |
| **User Interface** | ✅ Serves web pages | ❌ Internal only |

### Internal API Communication

The web server communicates with services server via REST API:

```bash
# Example internal API calls from web to services
POST localhost:8001/internal/storage/upload     # Stream file upload
GET  localhost:8001/internal/storage/download   # Retrieve file
DELETE localhost:8001/internal/storage/delete   # Delete file
POST localhost:8001/internal/storage/cleanup    # Cleanup operations
```

Authentication uses `INTERNAL_API_KEY` header.

## Development Benefits

### ✅ Advantages

- **Production Simulation**: Exact same behavior as production
- **Security Testing**: Web server never touches files
- **Stream Testing**: Can test large file uploads without local storage
- **PHI Compliance**: Proper tracking of which server handles what
- **Debugging**: Separate logs for web vs file operations

### 🔧 Development Features

- **Single Machine**: Both servers run on localhost
- **Easy Debugging**: Each server in separate tmux window
- **Hot Reload**: Both servers support code changes
- **Shared Database**: Both servers use same MariaDB instance
- **Easy Reset**: `tmux kill-session -t na` stops everything

## Testing File Uploads

### Manual Testing

1. **Start servers**: `tmna`
2. **Open browser**: `http://localhost:8000`
3. **Upload file** through any upload form
4. **Verify streaming**:
   - Check `django` window: should show API calls to services
   - Check `services` window: should show file save operations
   - Check `storage/workspace/`: should contain uploaded files

### Automated Testing

```bash
# Run streaming tests
python manage.py test depot.tests.test_streaming_simple

# Test two-server architecture
python manage.py test depot.tests.test_two_server
```

## Storage Locations

### File Storage
```
storage/workspace/          # All uploaded files (services server only)
├── uploads/               # Raw uploaded files
├── processed/            # Processed DuckDB files
└── temp/                 # Temporary processing files
```

### Logs
```
# Web server logs (tmux django window)
[timestamp] "POST /upload HTTP/1.1" 200    # User upload received
[timestamp] Streaming to services server   # File streamed

# Services server logs (tmux services window)  
[timestamp] Internal API: file upload      # File received from web
[timestamp] Saved file to storage/workspace # File stored locally
```

## Troubleshooting

### Common Issues

**Port Already in Use**
```bash
# Kill existing processes
lsof -ti :8000 | xargs kill -9
lsof -ti :8001 | xargs kill -9
```

**API Key Mismatch**
- Ensure both servers use same `INTERNAL_API_KEY`
- Check tmux windows for environment variable output

**Services Server Not Responding**
```bash
# Check services server status
curl -H "X-Internal-API-Key: dev-streaming-key-123" \
     http://localhost:8001/internal/storage/status
```

**File Not Found Errors**
- Web server can't see files in `storage/workspace/`
- Must use services server API to access files
- Check `relevant_files` in logs for file paths

### Debugging Commands

```bash
# Check storage configuration
python manage.py shell -c "
from depot.storage.manager import StorageManager
storage = StorageManager.get_workspace_storage()
print(f'Type: {type(storage).__name__}')
print(f'Config: {storage.__dict__ if hasattr(storage, \"__dict__\") else \"N/A\"}')
"

# Test streaming manually
python manage.py test_two_server --web-port 8000 --services-port 8001 --run-tests
```

## Production Deployment

### Key Differences

| Aspect | Development | Production |
|--------|-------------|------------|
| **Servers** | Same machine, different ports | Different machines |
| **Networking** | localhost:8001 | Internal network/VPN |
| **Storage** | Local filesystem | NAS mount or S3 |
| **SSL** | HTTP | HTTPS with certificates |
| **API Key** | `dev-streaming-key-123` | Secure generated key |

### Environment Variables for Production

```bash
# Web Server
SERVER_ROLE=web
INTERNAL_API_KEY=<secure-production-key>
SERVICES_SERVER_URL=https://services.internal.domain

# Services Server  
SERVER_ROLE=services
INTERNAL_API_KEY=<secure-production-key>
NAS_WORKSPACE_PATH=/mnt/nas/naaccord/workspace
```

## Quick Reference

### Start Development
```bash
dockerna start  # Start Docker services
tmna           # Start tmux session with streaming
```

### Access Points
- **Web Interface**: http://localhost:8000
- **Services API**: http://localhost:8001 (internal only)
- **Flower**: http://localhost:5555
- **MinIO**: http://localhost:9000

### Stop Development
```bash
tmux kill-session -t na  # Stop all tmux windows
dockerna stop           # Stop Docker services
```

### Test Streaming
```bash
python manage.py test depot.tests.test_streaming_simple
```