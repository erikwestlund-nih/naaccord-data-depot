# NA-ACCORD Data Depot

Clinical research data validation and storage platform using Django, R, and DuckDB.

## 🚨 CRITICAL: NEVER RESET THE PRODUCTION DATABASE

**THE PRODUCTION DATABASE CONTAINS REAL RESEARCH DATA. NEVER RESET IT.**

This system is now in production with real cohort submissions and user data. Database resets are **NEVER** acceptable on production or staging environments with real data.

**What to do instead when adding cohorts, users, or memberships:**

```bash
# ✅ CORRECT: Add data incrementally (does NOT delete existing data)
python manage.py seed_from_csv --model depot.Cohort --file resources/data/seed/cohorts.csv
python manage.py load_production_users

# ❌ WRONG: NEVER run these on production
# python manage.py reset_db
# python manage.py reset_dev_complete
# ansible-playbook ... database-reset.yml  # DESTROYS ALL DATA
```

**The `database-reset.yml` playbook DESTROYS ALL DATA. It is only for:**
- Initial server setup (empty database)
- Local development environments
- Test environments with no real data

**If you need to add a new cohort or user to production:**
1. Update the seed CSV files
2. Deploy the code changes
3. Run incremental seed commands (NOT reset commands)

---

## ⚠️ CRITICAL: Deployment Paths

**IMPORTANT - Repository deploys to `/opt/naaccord/depot/` on servers:**

```bash
# Repository structure ON SERVERS:
/opt/naaccord/depot/          # ✅ Git repo root
├── depot/                    # Django app directory (settings.BASE_DIR is /opt/naaccord/depot/depot/)
├── deploy/                   # ✅ Deployment code
│   └── ansible/             # ✅ Ansible playbooks: /opt/naaccord/depot/deploy/ansible/
├── manage.py                 # Django management
├── docker-compose.prod.yml   # Production containers
└── ...
```

**When referencing paths in documentation or commands:**
- ✅ `/opt/naaccord/depot/` (repo root)
- ✅ `/opt/naaccord/depot/depot/` (Django app subdirectory - yes, depot/depot is correct!)
- ✅ `/opt/naaccord/depot/deploy/ansible/` (Ansible playbooks)

## ⚠️ CRITICAL: Container Build Workflow

**NEVER build Docker containers on the user's development machine without explicit permission.**

**Correct workflow when container changes are needed:**

1. **Make the code change** (edit Dockerfile, entrypoint scripts, etc.)
2. **Commit and push** the changes to git
3. **ASK THE USER**: "I need to rebuild the [container-name] container. Should I wait for you to build and push it, or would you like me to provide build instructions?"
4. **Wait for user response** - they will either:
   - Build and push on their amd64 machine
   - Give you explicit permission to build

**Why this matters:**
- User's dev machine may be wrong architecture (arm64 vs amd64)
- Building containers is resource-intensive
- User may have their own build workflow/CI pipeline
- User prefers to control when containers are built and pushed

**When user builds containers:**
```bash
# User builds on their amd64 machine
docker build --platform linux/amd64 -t ghcr.io/jhbiostatcenter/naaccord/[container]:latest -f [path/to/Dockerfile] .
docker push ghcr.io/jhbiostatcenter/naaccord/[container]:latest
```

**Available containers:**
- `wireguard` - WireGuard VPN tunnel (deploy/containers/wireguard/Dockerfile)
- `web` - Django web server (deploy/containers/web/Dockerfile)
- `services` - Django services/API (deploy/containers/services/Dockerfile)
- `nginx` - Nginx reverse proxy (deploy/containers/nginx/Dockerfile)

## ⚠️ CRITICAL: Git Commit Authorship

**ALL commits must be authored by the human user who is responsible for the code.**

### Commit Authorship Policy

**The user is the author of all commits:**
- The user is **legally and professionally responsible** for all code changes
- AI assistance is a tool, like an IDE or linter - the user makes all final decisions
- Commits represent the user's work and professional contributions
- The user reviews, approves, and takes ownership of all changes

**NEVER create commits with AI/Claude as the author:**
```bash
# ❌ WRONG - Never do this
git commit --author="Claude <noreply@anthropic.com>" -m "message"

# ✅ CORRECT - Always commit as the user
git commit -m "message"  # Uses user's git config
```

### Optional: Acknowledging AI Assistance

Users may optionally acknowledge AI assistance in commit messages for transparency:

```bash
# Optional acknowledgment in commit message body
git commit -m "feat: implement patient ID validation

Added cross-file patient ID validation to ensure data integrity
across submission files.

AI-assisted with Claude Code"
```

**This is the user's choice** - they may acknowledge AI assistance or not. The key principle is that **the user is always the commit author** because they are responsible for the work.

### Why This Matters

1. **Legal Responsibility**: Commits represent intellectual property and legal responsibility
2. **Professional Record**: Git history is the user's professional contribution record
3. **Code Ownership**: The user owns and maintains the codebase
4. **Accountability**: Clear attribution for code decisions and changes
5. **Team Collaboration**: Other developers need to know who to consult about changes

### Implementation

When creating commits through AI assistance:
1. **Stage changes**: `git add <files>`
2. **Write clear commit message**: Describe what and why
3. **Commit as user**: Use standard `git commit` (inherits user's git config)
4. **Optional**: Mention AI assistance in commit body if desired
5. **Push changes**: `git push origin <branch>`

The user's git configuration (name and email) will automatically be used as the commit author.

## Project Overview

NA-ACCORD (North American AIDS Cohort Collaboration on Research and Design) Data Depot validates and stores clinical research data submissions. The system combines Python/Django for web infrastructure with R/NAATools for statistical validation and report generation.

### Key Technologies
- **Backend**: Django 5.x with Celery for async processing
- **Data Processing**: R (NAATools package) + DuckDB for large datasets
- **Frontend**: Vite + Tailwind CSS + Alpine.js + HTMX
- **Storage**: NAS network storage for reports, MariaDB for metadata (driver architecture supports future S3-compatible migration)

## 🔄 Documentation Maintenance (CRITICAL)

**After every code change, systematically verify documentation is up to date:**

1. **Check directory-specific CLAUDE.md files** in the code area you modified:
   - `depot/models/CLAUDE.md` - After changing models
   - `depot/management/commands/CLAUDE.md` - After adding/modifying commands
   - `depot/tasks/CLAUDE.md` - After changing Celery tasks
   - `depot/views/CLAUDE.md` - After modifying views
   - `depot/storage/CLAUDE.md` - After changing storage drivers
   - `depot/tests/CLAUDE.md` - After adding/modifying tests

2. **Update main CLAUDE.md** if changes affect:
   - Architecture patterns
   - Key features or workflows
   - Development setup
   - Important conventions

3. **Update pattern files** in the relevant sections:
   - `## Key Patterns` section (Core, Development, Features, Security)
   - Ensure examples match current implementation

**This is not optional - outdated documentation causes confusion and errors.**

## Architecture Highlights

NA-ACCORD uses a sophisticated PHI-compliant architecture designed for healthcare data processing with comprehensive audit trails and security boundaries.

### Two-Server PHI-Compliant Architecture

**Production Deployment:**
```
Web Server (10.150.96.6)                Services Server (10.150.96.37)
┌─────────────────────────┐             ┌─────────────────────────┐
│ Nginx → Django Web      │             │ Django API + Celery     │
│         ↓               │             │         ↓               │
│ WireGuard Container ────┼──── PHI ────┼──→ WireGuard Container  │
│ (10.100.0.10)          │ Encrypted   │    (10.100.0.11)       │
└─────────────────────────┘             └─────────────────────────┘
                                                  ↓
                                        ┌─────────────────────────┐
                                        │ MariaDB (Encrypted)     │
                                        │ Redis Cache             │
                                        │ R/Quarto Processing     │
                                        │ NAS Mount               │
                                        └─────────────────────────┘
```

**Key Security Features:**
- **PHI Isolation**: Web server never stores PHI data locally
- **Encrypted Tunnels**: ChaCha20-Poly1305 WireGuard encryption for all PHI traffic
- **Database Encryption**: MariaDB encryption at rest with key rotation
- **Comprehensive Audit**: PHIFileTracking system logs every file operation
- **Storage Abstraction**: Multi-driver system (local/S3/remote) with automatic selection

### Data Audit Workflow
1. User uploads data file (CSV/TSV) via web interface
2. **StorageManager routes to appropriate storage** (RemoteStorageDriver on web server)
3. Celery task converts to DuckDB format (handles up to 40M rows/2GB)
4. **PHIFileTracking logs every operation** with comprehensive audit trail
5. R-based audit process validates against JSON definition
6. Quarto notebook generates HTML report with statistics and visualizations
7. Report stored via StorageManager with time-limited access URLs

### Upload Submission System
Multi-file submission workflow with version tracking:
- **Patient File First**: Patient files establish ID universe for validation
- **Version Management**: Each file supports multiple versions with history
- **Cross-File Validation**: Non-patient files validated against patient ID universe
- **Table-Level Sign-off**: Individual data tables signed off independently
- **Warning-Based Validation**: Issues generate warnings but don't block submission

### Storage Manager Abstraction
Sophisticated multi-driver storage system:
- **Server Role Detection**: Automatically selects driver based on SERVER_ROLE
- **Web Server**: Uses RemoteStorageDriver to stream to services server
- **Services Server**: Uses NAS storage for actual file operations (driver architecture supports future S3-compatible migration)
- **Submission Storage**: NAS network storage for permanent file storage
- **Scratch Storage**: Temporary processing files with automatic cleanup

### PHI File Tracking System
Complete audit trail for HIPAA compliance:
- **20+ Action Types**: Tracks creation, deletion, conversion, streaming operations
- **Cleanup Management**: Monitors temporary file cleanup with overdue detection
- **Multi-Server Support**: Tracks operations across web and services servers
- **Integrity Verification**: Commands to verify file existence and corruption
- **Error Logging**: Comprehensive error capture for failed operations

### Data Definitions
- JSON format specifying structure, validators, and summarizers
- Types: id, string, date, enum, boolean, int, float, year
- Validators: required, date format, ranges, conditional logic
- Summarizers: statistics, histograms, bar charts

## Development Setup

### ⭐ RECOMMENDED: 5-Minute Quick Start

**Get a fully working development environment in under 5 minutes:**

```bash
# 1. Start services with Docker Compose
docker compose -f docker-compose.dev.yml up -d

# 2. Complete environment setup (creates everything!)
python manage.py reset_dev_complete --skip-confirmation
```

**That's it!** This creates:
- ✅ **15 test users** across all roles (admin, manager, researcher, viewer)
- ✅ **31 cohorts** with proper memberships
- ✅ **Complete database** with all required data
- ✅ **Clean storage** directories
- ✅ **Test submissions** ready for development

**Access the application:** http://localhost:8000

**Test accounts:** See `depot/fixtures/test_users/` for credentials

---

### 🚀 Alternative: Complete Environment Reset

For resetting an existing environment:

```bash
# Complete reset - database, users, storage cleanup (4 seconds!)
python manage.py reset_dev_complete --skip-confirmation

# Interactive with confirmation
python manage.py reset_dev_complete
```

This creates **15 test users**, **11 cohort memberships**, cleans storage, and generates test data in under 5 seconds.

### 🐳 Docker Test Container Database Seeding

**IMPORTANT**: After testing with Docker test containers, ALWAYS reseed the database before acceptance testing:

```bash
# Inside services container - Full database reset and seeding (RECOMMENDED)
docker exec naaccord-test-services python manage.py reset_db && \
docker exec naaccord-test-services python manage.py migrate && \
docker exec naaccord-test-services python manage.py seed_init && \
docker exec naaccord-test-services python manage.py setup_permission_groups && \
docker exec naaccord-test-services python manage.py load_test_users && \
docker exec naaccord-test-services python manage.py assign_test_users_to_groups
```

**Why this is needed**: Docker containers start with an empty database. The manual seeding command chain is required because `reset_dev_complete` has foreign key protection issues in Docker environments. We use the **services** container because it has direct database access.

**What it creates**:
- ✅ **31 cohorts** (all NA-ACCORD cohorts loaded from seed data)
- ✅ All core data tables (data file types, protocol years, permission groups)
- ✅ **15 test users** across all roles (admins, managers, researchers, viewers)
- ✅ **9 users with cohort memberships** (users assigned to cohorts they can access)
- ✅ Proper group permissions for role-based access control

**Key Commands Explained**:
1. `seed_init` - **Loads 31 cohorts**, data file types, protocol years, and permission groups from CSV files
2. `setup_permission_groups` - Creates permission groups with proper Django permissions
3. `load_test_users` - Creates 15 test users and assigns them to cohorts
4. `assign_test_users_to_groups` - Assigns users to permission groups (critical for access control)

**Verification**: After seeding, users should see their cohorts in the sidebar when logged in. If cohorts don't appear, the seeding commands were not run or `assign_test_users_to_groups` was skipped.

### Alternative: Manual Service Start

```bash
# Start all services manually (or use tmux startup script)
/Users/erikwestlund/code/projects/tmux/start_naaccord.sh  # Automated tmux setup

# Or manually start services:
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


## Key Patterns


### Core

#### Data Definitions

**Defines JSON data definition structure, validators, summarizers, and migration from Python**

# Data Definitions
## Overview
Data definitions specify the structure, validation rules, and summarization methods for each data file type in NA-ACCORD.
## JSON Definition Structure
### Required Fields
```json
{
  "name": "variableName",        // Variable identifier
  "type": "string",              // Data type
  "description": "Description"   // Human-readable description
}
```
### Optional Fields
```json
{
  "value_optional": true,        // Whether value can be missing
  "value_required": false,       // Alternative to value_optional
  "allowed_values": [],          // For enum types
  "validators": [],              // Validation rules
  "summarizers": [],             // Summary statistics/visualizations

#### Django Architecture

**Defines Django 5.x architecture patterns for models, views, forms, and Celery integration**

# Django Architecture
## Overview
NA-ACCORD uses Django 5.x with a custom architecture tailored for clinical data validation and storage.
## Key Patterns
### Models
- Custom User model extending Django's AbstractUser
- Key models: Audit, Notebook, DataFileType, Cohort, ValidationRun plus new summary hierarchy (`VariableSummary`, `DataTableSummary`, `SubmissionSummary`)
- Use `related_name` for all foreign keys
- Timestamps: created_at, updated_at on all models
### Views
- Function-based views for simplicity
- Login required decorator for all authenticated views
- Cohort-based access control checks
- HTMX integration for dynamic updates
### Forms
- Custom form classes with user context
- File upload handling with validation
- Dynamic field population based on user permissions
### Celery Integration
- Async task processing for:
  - Validation orchestration (per-variable execution)
  - Summary generation tasks (variable, data table, submission levels)

#### R Integration

**Defines R integration patterns using NAATools package, Quarto notebooks, and DuckDB**

# R Integration
## Overview
NA-ACCORD uses R through the NAATools package for data validation, summarization, and report generation.
## NAATools Package
### Installation & Development Mode
```r
# Production: Install from GitHub
remotes::install_github("JHBiostatCenter/naaccord-r-tools")
# Development: Use .r_dev_mode file
# Create .r_dev_mode with:
# NAATOOLS_DIR=$HOME/code/NAATools
```
### Key Functions
#### Definition Management
```r
# Read JSON definition
definition <- NAATools::read_definition("path/to/definition.json")
# Summarize definition structure
summary <- NAATools::summarize_definition(definition)
# Get specific variable definition


### Development

#### Build Workflow

**Defines frontend build system with Vite and backend management commands**

# Build Workflow
## Overview
NA-ACCORD uses modern build tools for frontend assets and management commands for backend setup.
## Frontend Build System
### Vite Configuration
```javascript
// vite.config.js
export default {
  build: {
    outDir: 'static',
    manifest: true,
    rollupOptions: {
      input: {
        main: resolve(__dirname, 'resources/js/app.js'),
        styles: resolve(__dirname, 'resources/css/app.css')
      }
    }
  }
}
```

#### Environment Setup

**Defines development environment setup including Python, R, Node.js, and service dependencies**

# Environment Setup
## Overview
NA-ACCORD requires Python, R, Node.js, and database components for full functionality.
## Prerequisites
### Python Environment
```bash
# Python 3.8 or later required
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```
### R Environment
```bash
# Install R (4.0+)
# Install required packages
R -e "install.packages(c('here', 'duckdb', 'dplyr', 'knitr', 'kableExtra', 'jsonlite', 'plotly', 'htmltools', 'htmlwidgets', 'devtools', 'remotes'))"
# Install NAATools
R -e "remotes::install_github('JHBiostatCenter/naaccord-r-tools')"
```
### Node.js Environment
```bash
# Install Node.js (18.x or later)
npm install  # Install frontend dependencies
npm run dev  # Start Vite dev server
```


### Features

#### Audit System

**Defines audit workflow architecture including file upload, DuckDB conversion, and report generation**

# Audit System
## Overview
The audit system validates uploaded data files against defined schemas and generates comprehensive reports.
## Workflow Architecture
### 1. File Upload
```python
# Form handles file upload and validation
form = AuditSubmissionForm(request.POST, request.FILES, user=request.user)
if form.is_valid():
    audit = form.handle_submission()  # Creates Audit record
    # Triggers Celery task
```
### 2. Audit Processing States
- `pending`: Initial state after upload
- `processing_duckdb`: Converting to DuckDB format
- `processing_notebook`: Running R notebook
- `completed`: Report available
- `failed`: Error occurred
### 3. Async Processing
```python

#### Data Processing

**Defines data processing patterns using DuckDB for analytics and NAATools for validation**

# Data Processing
## Overview
NA-ACCORD processes large clinical datasets using DuckDB for efficient analytics and NAATools for validation and summarization.
## DuckDB Integration
### File Conversion
```python
def load_duckdb(self):
    # Create temporary DuckDB file
    self.temp_dir = tempfile.mkdtemp()
    self.db_path = Path(self.temp_dir) / "audit_data.duckdb"
    # Connect and create table
    self.conn = duckdb.connect(str(self.db_path))
    # Load data with automatic type detection
    if self.data_file_type.name == "laboratory":
        self.conn.execute("""
            CREATE TABLE data AS 
            SELECT * FROM read_csv_auto(?, header=true)
        """, [self.data_content])
```
### Performance Optimization

#### Notebook System

**Defines Quarto notebook system for report generation with R code execution**

# Notebook System
## Overview
NA-ACCORD uses Quarto notebooks to generate dynamic HTML reports that combine R analysis with formatted output.
## Notebook Architecture
### Notebook Model
```python
class Notebook(models.Model):
    name = models.CharField(max_length=200)
    template_path = models.CharField(max_length=200)  # e.g., "audit/generic_audit.qmd"
    data_file_type = models.ForeignKey(DataFileType, on_delete=models.CASCADE)
    # Polymorphic relationship to any model
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')
    # Compilation tracking
    status = models.CharField(max_length=50, default='pending')
    compiled_at = models.DateTimeField(null=True)
    error = models.TextField(null=True)
    # Storage
    s3_key = models.CharField(max_length=500, null=True)

#### Upload Submission

**Multi-file clinical data submission workflow with validation, acknowledgment, and version tracking**

# Upload Submission System
## Overview
The Upload Submission system allows cohorts to submit complete datasets across multiple file types for a given submission wave. It builds on the existing audit system to provide validation while allowing flexible submission with documented issues.
## Key Concepts
### Submission Workflow
1. **Patient File First**: Cohorts must upload patient file first to establish valid patient IDs
2. **Flexible File Upload**: Other files can be uploaded in any order or skipped with reason
3. **Warning-Based Validation**: Issues are highlighted but don't block submission
4. **Acknowledgment Required**: Each file must be acknowledged with optional comments
5. **Final Sign-off**: Complete submission requires final acknowledgment
### Data Models
#### CohortSubmission
- Tracks overall submission for a cohort/wave combination
- Stores extracted patient IDs for cross-file validation
- Manages submission status: draft → in_progress → completed → signed_off
- Records final acknowledgment and comments
#### CohortSubmissionFile
- Represents individual file uploads within a submission
- Links to Audit for validation results
- Tracks versions for re-uploads


### Security

#### Data Security

**Defines security patterns for external data intake, audit trails, and cohort-based access control**

# Data Security
## Overview
NA-ACCORD implements a sophisticated security-first architecture for PHI (Protected Health Information) processing with comprehensive audit trails, encrypted data transit, and strict access controls. The system enforces HIPAA compliance through technical safeguards and complete audit tracking.

## PHI-Compliant Architecture
### Two-Server Security Model
The production deployment uses a strict separation between web and services tiers:

**Web Server Security:**
- **No PHI Storage**: Web server never stores PHI data locally
- **RemoteStorageDriver**: All file operations streamed to services server
- **WireGuard Encryption**: ChaCha20-Poly1305 encryption for all PHI traffic
- **Access Control**: Nginx with client certificate authentication

**Services Server Security:**
- **Encrypted Storage**: MariaDB encryption at rest with key rotation
- **PHI Processing**: All data processing occurs in secure environment
- **Audit Logging**: Complete PHIFileTracking for every operation
- **Network Isolation**: No direct internet access for processing services

### Storage Manager Security
Multi-driver storage system with automatic security boundaries:

```python
# Storage selection based on server role
def get_scratch_storage(cls):
    server_role = os.environ.get('SERVER_ROLE', '').lower()

    if server_role == 'web':
        # Web server MUST use remote driver
        return RemoteStorageDriver('scratch_remote')
    else:
        # Services server uses local/S3
        return LocalFileSystemStorage('scratch')
```

**Storage Security Features:**
- **Role-Based Driver Selection**: Automatic selection prevents PHI storage on web tier
- **API Authentication**: All remote operations use secure API keys
- **Encrypted Transit**: HTTPS for all remote storage operations
- **Access Logging**: Every storage operation logged for audit

### PHI File Tracking System
Comprehensive audit trail for HIPAA compliance:

```python
# Every PHI operation is tracked
PHIFileTracking.log_operation(
    cohort=cohort,
    user=user,
    action='nas_raw_created',
    file_path='/mnt/nas/submissions/cohort_123/patient_data.csv',
    file_type='raw_csv',
    file_size=1024000,
    content_object=audit_instance
)
```

**Tracking Features:**
- **Complete Audit Trail**: 20+ action types covering all PHI operations
- **Multi-Server Tracking**: Operations tracked across web and services servers
- **Cleanup Verification**: Mandatory tracking of temporary file cleanup
- **Integrity Checks**: Regular verification of file existence and corruption
- **Error Logging**: Comprehensive error capture for failed operations

**Management Commands for Security:**
```bash
# Show complete PHI audit trail
python manage.py show_phi_audit_trail --cohort 5 --days 7

# Verify PHI file integrity
python manage.py verify_phi_integrity --check-hashes

# Verify cleanup completion
python manage.py verify_phi_cleanup
```

## External Data Intake Security
### Key Principles
1. **All data comes from external sources** - Never assume internal generation
2. **Complete audit trail** - Track every temporary file for mandatory cleanup
3. **Microservice architecture** - Prepare for isolated, secure processing environment
4. **Zero web accessibility** - Data processing occurs in secure, non-web-accessible zones
5. **PHI Isolation** - Web tier never stores PHI data locally

### Secure Upload Workflow
```python
def secure_upload_process(uploaded_file, cohort, user):
    # 1. Initial PHI tracking
    PHIFileTracking.log_operation(
        cohort=cohort,
        user=user,
        action='file_uploaded_via_stream',
        file_path=temp_path,
        file_type='raw_csv'
    )

    # 2. Stream to services server (if on web server)
    storage = StorageManager.get_scratch_storage()
    secure_path = storage.save(temp_path, content)

    # 3. Track storage operation
    PHIFileTracking.log_operation(
        cohort=cohort,
        user=user,
        action='work_copy_created',
        file_path=secure_path,
        cleanup_required=True,
        expected_cleanup_by=timezone.now() + timedelta(hours=2)
    )

    # 4. Process in secure environment
    process_upload_precheck.delay(secure_path)
```

### Access Control and Authentication
- **Cohort-Based Access**: Users can only access data from their assigned cohorts
- **Role-Based Permissions**: Site admins, cohort users, and read-only access levels
- **SAML Integration**: Enterprise authentication with group mapping
- **API Key Security**: Internal API keys for server-to-server communication

### Compliance Features
- **HIPAA Audit Trail**: Complete logging of all PHI access and operations
- **Data Minimization**: Only necessary data fields are processed and stored
- **Retention Controls**: Automated cleanup of temporary files and expired data
- **Access Logging**: User activity tracking for compliance reporting


## Management Commands

### Database Management

**CRITICAL: Complete Database Reset and Setup**

⚠️ **IMPORTANT**: The most common issue after database reset is users not seeing cohorts in the sidebar. This happens when `CohortMembership` records are missing.

**🐳 FOR DOCKER CONTAINERS:**
```bash
# Use services container for database operations (has direct database access)
docker exec naaccord-test-services python manage.py reset_db && \
docker exec naaccord-test-services python manage.py migrate && \
docker exec naaccord-test-services python manage.py seed_init && \
docker exec naaccord-test-services python manage.py setup_permission_groups && \
docker exec naaccord-test-services python manage.py load_test_users && \
docker exec naaccord-test-services python manage.py assign_test_users_to_groups
```
This loads **31 cohorts** and creates **15 users** with **9 cohort memberships**. See [Docker Test Container Database Seeding](#-docker-test-container-database-seeding) for details.

**🎯 FOR LOCAL DEVELOPMENT (Use This):**
```bash
# Complete environment setup (fixes cohort visibility issue)
python manage.py setup_complete_environment --reset-db
```

**Manual Step-by-Step (if needed):**
```bash
# 1. Reset database (drops all tables)
python manage.py reset_db

# 2. Run migrations (creates all Django and app tables)
python manage.py migrate

# 3. Seed basic data (cohorts, data file types, protocol years)
python manage.py seed_init

# 4. Setup permission groups and roles
python manage.py setup_permission_groups

# 5. Load test users with proper associations
python manage.py load_test_users

# 6. Assign users to groups (critical for cohort sidebar display)
python manage.py assign_test_users_to_groups

# 7. Generate simulation data (test submissions, etc.)
python manage.py generate_sim_data
```

**Quick Commands:**
- `python manage.py reset_dev_complete` - **🚀 BEST**: Complete reset (4 seconds, 15 users, storage cleanup)
- `python manage.py setup_complete_environment` - Complete setup with cohort memberships
- `python manage.py setup_complete_environment --reset-db` - Reset DB + complete setup
- `python manage.py build_test_env` - Legacy command (may miss cohort memberships)
- `python manage.py reset_db` - Drop and recreate database
- `python manage.py seed_init` - Seed initial data from CSVs
- `python manage.py generate_sim_data` - Generate test data

**Critical Note:** If cohorts don't appear in the sidebar after database reset, it's because user-group associations in `depot_user_groups` table are missing. Always run `assign_test_users_to_groups` after any database reset.

**🏭 ADDING DATA TO PRODUCTION (Incremental - SAFE):**

To add new cohorts, users, or memberships to production WITHOUT destroying existing data:

```bash
# SSH to services server
ssh mrpznaaccorddb01.hosts.jhmi.edu

# Add new cohorts (will skip existing ones)
sudo docker exec naaccord-services python manage.py seed_from_csv --model depot.Cohort --file resources/data/seed/cohorts.csv

# Add/update production users and memberships
sudo docker exec -e NAACCORD_ENVIRONMENT=production naaccord-services python manage.py load_production_users
```

**🚨 INITIAL SETUP ONLY (DESTROYS ALL DATA):**

The `database-reset.yml` playbook is ONLY for initial server setup with an empty database. **NEVER use it on a production system with real data.**

```bash
# ⚠️ DANGER: Only for initial setup - DESTROYS ALL DATA
cd /opt/naaccord/depot/deploy/ansible
ansible-playbook -i inventories/production/hosts.yml playbooks/database-reset.yml --connection local --ask-vault-pass
# You must type "DELETE ALL DATA" to confirm
```

### Complete Development Reset Command

**NEW:** Use the comprehensive Django management command:

```bash
# Complete reset - everything in one command
python manage.py reset_dev_complete

# With options
python manage.py reset_dev_complete --skip-confirmation --skip-storage-cleanup
```

This single command replaces all the manual steps above and includes:
- Database reset and migrations
- All seeding commands (init, users, groups, assignments)
- Storage cleanup (including NAS mount)
- Test data generation
- Verification steps

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
└── NAATools/             # R package (local dev)
```

## Important Notes

- All patient data must be de-identified (cohortPatientId only)
- Cohort-based access control enforced at all levels
- Large file processing uses DuckDB for efficiency
- R code executes in isolated environment via Quarto
- Reports are self-contained HTML with embedded visualizations

## Server Deployment

### Quick Deployment Command

When logged into staging or production servers, use:

```bash
deployna
```

This single command deploys the latest code, copies static assets, and restarts all containers.

**Other helpful aliases available on servers:**
- `nahelp` - Show all available aliases
- `nalogs` - View all container logs
- `nastatus` - Show container status
- `nahealth` - Check application health
- `cdna` - Navigate to /opt/naaccord/depot

**See [deploy/docs/aliases-reference.md](deploy/docs/aliases-reference.md) for complete reference.**

### Deployment Documentation

For complete deployment procedures, see:
- **[deploy/CLAUDE.md](deploy/CLAUDE.md)** - Deployment domain overview
- **[deploy/deploy-steps.md](deploy/deploy-steps.md)** - Step-by-step deployment guide
- **[deploy/scripts/README.md](deploy/scripts/README.md)** - Bootstrap scripts
- **[deploy/docs/aliases-reference.md](deploy/docs/aliases-reference.md)** - Shell aliases reference

### Production Debugging

**IMPORTANT: Always prefix Docker commands with `sudo` on production servers.**

```bash
# Common debugging patterns (all require sudo on production):
sudo docker ps | grep naaccord                    # Check running containers
sudo docker logs <container-id> -f               # Follow logs
sudo docker exec <container-id> ps aux           # Check processes
sudo docker inspect <container-id>               # Container details
sudo docker compose -f docker-compose.prod.yml ps  # Service status
```

See [deploy/docs/troubleshooting.md](deploy/docs/troubleshooting.md) for complete debugging guide.

## UI Development Rules

- **ALWAYS use Alpine.js** for reactive UI components instead of vanilla JavaScript DOM manipulation
  - Use `x-data` for component state
  - Use `x-for` for lists
  - Use `x-if`/`x-show` for conditional rendering
  - Use `@click` for event handlers
  - Keep state management in Alpine components, not global JavaScript
- Use Django templates for server-side rendering with Alpine.js for interactivity
