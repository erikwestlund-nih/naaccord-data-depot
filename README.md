# NA-ACCORD Data Depot

Clinical research data validation and storage platform for [NA-ACCORD](https://naaccord.org/). This Django application validates clinical data submissions against research protocol requirements and generates comprehensive audit reports.

## Quick Start

### Prerequisites

- Python 3.12 or later
- Docker and Docker Compose (for local development)
- Node.js 18.x or later (for frontend assets)

### 5-Minute Setup

```bash
# 1. Clone and navigate
git clone https://github.com/erikwestlund/naaccord-depot/ naaccord
cd naaccord

# 2. Create Python virtual environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. Copy environment configuration
cp .env.example .env

# 4. Start services with Docker Compose
docker compose -f docker-compose.dev.yml up -d

# 5. Build complete test environment (database, users, test data)
python manage.py reset_dev_complete --skip-confirmation
```

Access the application at http://localhost:8000

**Test Accounts**: See `depot/fixtures/test_users/` for credentials.

### What Was Created

- **31 cohorts** loaded from seed data
- **15 test users** across all roles (admin, manager, researcher, viewer)
- **Complete database** with proper permissions and group assignments
- **Clean storage** directories ready for development
- **Test submissions** for immediate development

## Key Technologies

- **Backend**: Django 5.x with Celery for async processing
- **Data Processing**: R (NAATools package) + DuckDB for large datasets (up to 40M rows)
- **Frontend**: Vite + Tailwind CSS + Alpine.js
- **Storage**: NAS network storage for reports, MariaDB for metadata
- **Infrastructure**: Ansible for automated deployment and configuration management
- **Security**: PHI-compliant two-server architecture with WireGuard encryption

## Architecture Overview

NA-ACCORD uses a sophisticated PHI-compliant architecture:

```
Web Server                    Services Server
┌─────────────────┐          ┌─────────────────────┐
│ Django Web      │   PHI    │ Django API + Celery │
│ Nginx           │ ──────→  │ R/Quarto Processing │
│ (No PHI stored) │ Encrypted│ MariaDB (encrypted) │
└─────────────────┘          └─────────────────────┘
```

**Key Security Features:**
- **PHI Isolation**: Web server never stores PHI data locally
- **Encrypted Tunnels**: WireGuard encryption for all PHI traffic
- **Complete Audit Trail**: PHIFileTracking logs every file operation
- **HIPAA Compliance**: Comprehensive security and audit systems

## Data Workflow

1. User uploads clinical data file (CSV/TSV)
2. Async conversion to DuckDB format (handles up to 2GB files)
3. R-based validation against JSON data definitions
4. Quarto notebook generates HTML report with statistics and visualizations
5. Report stored on NAS with time-limited access URLs

## Data Definitions

Clinical data tables are defined in JSON format with validators and summarizers:

```json
{
  "name": "cohortPatientId",
  "type": "id",
  "description": "Unique patient identifier",
  "validators": ["required", "no_duplicates"],
  "summarizers": ["count", "unique"]
}
```

**Supported Types**: id, string, date, enum, boolean, int, float, year

**See Complete Documentation**:
- **[Validators Reference](docs/reference/validators.md)** - All validation rules
- **[Summarizers Reference](docs/reference/summarizers.md)** - Statistical summaries
- **[Data Definitions Guide](docs/technical/data-definitions.md)** - Creating definitions

## Development

### Running Services Manually

```bash
# Terminal 1: Django web server
export SERVER_ROLE=web INTERNAL_API_KEY=test-key-123 SERVICES_URL=http://localhost:8001
python manage.py runserver 0.0.0.0:8000

# Terminal 2: Services server
export SERVER_ROLE=services INTERNAL_API_KEY=test-key-123
python manage.py runserver 0.0.0.0:8001

# Terminal 3: Celery worker
celery -A depot worker -l info

# Terminal 4: Frontend dev server
npm run dev
```

### Automated Tmux Setup (Optional)

For convenience, you can create a tmux startup script to launch all services:

```bash
#!/bin/bash
# Example: scripts/start_dev.sh

SESSION="naaccord"

# Create new tmux session
tmux new-session -d -s $SESSION -n shell

# Create windows for each service
tmux new-window -t $SESSION:1 -n django
tmux new-window -t $SESSION:2 -n services
tmux new-window -t $SESSION:3 -n celery
tmux new-window -t $SESSION:4 -n npm

# Start Django web server
tmux send-keys -t $SESSION:1 "source venv/bin/activate" C-m
tmux send-keys -t $SESSION:1 "export SERVER_ROLE=web INTERNAL_API_KEY=test-key-123 SERVICES_URL=http://localhost:8001" C-m
tmux send-keys -t $SESSION:1 "python manage.py runserver 0.0.0.0:8000" C-m

# Start Django services server
tmux send-keys -t $SESSION:2 "source venv/bin/activate" C-m
tmux send-keys -t $SESSION:2 "export SERVER_ROLE=services INTERNAL_API_KEY=test-key-123" C-m
tmux send-keys -t $SESSION:2 "python manage.py runserver 0.0.0.0:8001" C-m

# Start Celery worker
tmux send-keys -t $SESSION:3 "source venv/bin/activate" C-m
tmux send-keys -t $SESSION:3 "celery -A depot worker -l info" C-m

# Start frontend dev server
tmux send-keys -t $SESSION:4 "npm run dev" C-m

# Attach to session
tmux attach -t $SESSION
```

### Useful Management Commands

```bash
# Complete environment reset
python manage.py reset_dev_complete

# Individual operations
python manage.py reset_db                      # Drop and recreate database
python manage.py migrate                       # Run migrations
python manage.py seed_init                     # Load cohorts and base data
python manage.py load_test_users               # Create test users
python manage.py assign_test_users_to_groups   # Assign permissions
python manage.py generate_sim_data             # Create test submissions
```

**IMPORTANT**: After database reset, always run `assign_test_users_to_groups` or users won't see cohorts in the sidebar.

## Frontend Development

```bash
# Install dependencies
npm install

# Development with hot reload
npm run dev

# Production build
npm run build
```

**Technologies**:
- **Tailwind CSS**: Utility-first styling (configured in `tailwind.config.js`)
- **Alpine.js**: Lightweight reactive components
- **Vite**: Fast build system with HMR

## Testing

### Running Tests

```bash
# Run complete test suite with SQLite backend (fast)
python manage.py test depot.tests --settings=depot.test_settings

# Run specific test file
python manage.py test depot.tests.services.test_file_upload_service --settings=depot.test_settings

# Run with verbose output
python manage.py test depot.tests --settings=depot.test_settings -v 2

# Keep database between runs (faster for repeated testing)
python manage.py test depot.tests --settings=depot.test_settings --keepdb

# Run specific test method
python manage.py test depot.tests.services.test_file_upload_service.TestFileUploadService.test_calculate_file_hash --settings=depot.test_settings
```

### Test Coverage

The automated test suite includes comprehensive coverage across multiple domains:

**Security Tests (62 tests)**:
- Path traversal prevention in storage drivers (34 tests)
- SQL injection protection via Django ORM (10 tests)
- XSS prevention with template auto-escaping (5 tests)
- API authentication and authorization (2 tests)
- Session security configuration (3 tests)
- File upload validation and size limits (3 tests)
- Rate limiting configuration (3 tests)
- Access control and cohort membership (2 tests)

**Service Layer Tests**:
- File upload and validation services
- Storage driver operations (local, remote, NAS)
- PHI file tracking and audit trail
- Hash calculation and file integrity

**Model Tests**:
- Data integrity and relationships
- Custom model methods and managers
- Validation logic

**View Tests**:
- HTTP request/response handling
- Permission checks and access control
- Form validation

**Test Organization**:
- `depot/tests/services/` - Service class tests
- `depot/tests/views/` - View function tests
- `depot/tests/models/` - Model method tests
- `depot/tests/test_*_security.py` - Security test suite

All tests use SQLite for speed and run without requiring MySQL permissions.

## Deployment

### Quick Deployment

On staging or production servers:

```bash
deployna  # Single command deploys latest code and restarts containers
```

**Other helpful aliases**:
- `nahelp` - Show all available aliases
- `nalogs` - View container logs
- `nastatus` - Container status
- `nahealth` - Application health check

### Deployment Automation with Ansible

NA-ACCORD uses Ansible for infrastructure automation and configuration management across staging and production environments.

**Ansible Structure:**
```
deploy/ansible/
├── inventories/
│   ├── staging/
│   │   ├── hosts.yml          # Staging server inventory
│   │   └── group_vars/
│   │       └── vault.yml      # Encrypted secrets (staging)
│   └── production/
│       ├── hosts.yml          # Production server inventory
│       └── group_vars/
│           └── vault.yml      # Encrypted secrets (production)
├── playbooks/
│   ├── services-server.yml    # Full services server deployment
│   ├── web-server.yml         # Full web server deployment
│   ├── deploy.yml             # Application code updates
│   └── database-reset.yml     # Database reset and seeding
└── roles/                     # Reusable Ansible roles
```

**Ansible Vault and Secrets Management:**

All sensitive configuration (database passwords, API keys, SSL certificates) is encrypted using Ansible Vault:

```bash
# View encrypted secrets (requires vault password)
ansible-vault view deploy/ansible/inventories/staging/group_vars/vault.yml

# Edit encrypted secrets
ansible-vault edit deploy/ansible/inventories/staging/group_vars/vault.yml

# Run playbook with vault password
ansible-playbook -i inventories/staging/hosts.yml \
  playbooks/deploy.yml \
  --vault-password-file ~/.naaccord_vault_staging
```

**What's Stored in Vault:**
- MariaDB root and application passwords
- Django SECRET_KEY
- Internal API authentication keys
- SAML credentials and certificates
- WireGuard private keys
- NAS mount credentials

**Environment-Specific Playbooks:**

Each environment (staging/production) has its own encrypted vault file. Playbooks automatically use the correct secrets based on the inventory file specified.

### Deployment Documentation

- **[deploy/CLAUDE.md](deploy/CLAUDE.md)** - Deployment domain overview for LLM agents
- **[deploy/deploy-steps.md](deploy/deploy-steps.md)** - Step-by-step deployment
- **[deploy/docs/aliases-reference.md](deploy/docs/aliases-reference.md)** - Shell aliases
- **[deploy/scripts/README.md](deploy/scripts/README.md)** - Bootstrap scripts

## Complete Documentation

### Core Documentation
- **[CLAUDE.md](CLAUDE.md)** - Main development guide with architecture details for LLM agents
- **[docs/README.md](docs/README.md)** - Documentation navigation hub

### Reference Documentation
- **[Validators Reference](docs/reference/validators.md)** - Complete validator documentation
- **[Summarizers Reference](docs/reference/summarizers.md)** - Complete summarizer documentation
- **[Data Definitions](docs/technical/data-definitions.md)** - Creating JSON definitions

### Technical Documentation
- **[Upload Submission Workflow](docs/technical/upload-submission-workflow.md)**
- **[Storage Manager Abstraction](docs/technical/storage-manager-abstraction.md)**
- **[File Streaming Architecture](docs/technical/file-streaming.md)**
- **[R Integration](docs/technical/r-integration.md)**

### Security Documentation
- **[PHI File Tracking System](docs/security/PHIFileTracking-system.md)**
- **[WireGuard VPN Setup](docs/security/wireguard.md)**
- **[Security Architecture](docs/security/security-overview.md)**

### Deployment & Operations
- **[Production Deployment](docs/manuals/deployment/guides/deployment-workflow.md)**
- **[Development Setup](docs/manuals/deployment/guides/architecture.md)**

## Project Structure

```
naaccord/
├── depot/                 # Main Django app
│   ├── models/           # Django models
│   ├── views/            # View functions
│   ├── tasks/            # Celery tasks
│   ├── data/
│   │   ├── definitions/  # JSON data definitions
│   │   └── auditor.py    # Audit processing logic
│   ├── notebooks/        # Quarto report templates
│   └── R/                # R utility functions
├── resources/            # Frontend source (Vite)
├── static/               # Built frontend assets
├── deploy/               # Deployment automation
└── docs/                 # Documentation
```

## Important Notes

- All patient data must be de-identified (cohortPatientId only)
- Cohort-based access control enforced at all levels
- Large file processing uses DuckDB for efficiency (handles 40M rows / 2GB files)
- R code executes in isolated environment via Quarto
- Reports are self-contained HTML with embedded visualizations
- Complete PHI audit trail for HIPAA compliance

## Authors

This project was created by Erik Westlund, with contributions from the NA-ACCORD team.

* Erik Westlund, ewestlund@jhu.edu
* Andre Hackman, ahackman@jhu.edu
* Fred Van Dyk, fvandyk2@jhu.edu

## License

This is proprietary software created by the Johns Hopkins Biostatistics Center (JHBC) for NA-ACCORD. For questions or inquiries, please contact the NA-ACCORD team.
