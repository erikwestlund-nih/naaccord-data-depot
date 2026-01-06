# NA-ACCORD Documentation

**Complete documentation for the NA-ACCORD clinical research data validation platform**

## 📁 Directory Structure

### `/deployment/` - Deployment & Infrastructure

**Primary Guides:**
- **`production.md`** - Comprehensive HIPAA-compliant production deployment (two-server architecture)
- **`development.md`** - Complete local development setup with tmux session management
- **`ansible.md`** - Consolidated Ansible deployment guide (remote & local execution strategies)

**Supporting Documentation:**
- `deployment-checklist.md` - Pre-deployment verification checklist
- `deployment-commands.md` - Common deployment commands reference

**Subdirectories:**
- `containers/` - Container build and optimization documentation
  - `docker.md` - Docker environment setup and configuration
  - `compose.md` - Docker Compose configuration comparison
  - `optimization.md` - Container performance improvements
- `tools/` - Development and build tools
  - `tmux.md` - Tmux development session management
  - `tmux-recovery.md` - Tmux session recovery procedures
  - `vm-builds.md` - Virtual machine build instructions for containers

### `/security/` - Security & Compliance
PHI compliance, authentication, encryption, and audit systems:

**Core Security:**
- **`PHIFileTracking-system.md`** - Comprehensive PHI audit trail system (HIPAA compliance)
- **`wireguard.md`** - WireGuard VPN implementation for PHI encryption
- **`api-keys.md`** - API key rotation strategies and management
- **`https-internal.md`** - Internal HTTPS architecture for server-to-server communication

**Authentication:**
- `auth-workflow.md` - Authentication workflow and SAML integration
- `saml-testing.md` - SAML authentication testing procedures
- `test-accounts.md` - Test user accounts and access patterns

**Compliance:**
- `logging/` - Logging compliance for healthcare environments
  - `compliance.md` - Complete logging compliance implementation
  - `jhu-requirements.md` - Johns Hopkins IT security requirements analysis
  - `sensitive-data.md` - Sensitive data handling in logs
- `deployment-todos.md` - Security deployment checklist

### `/technical/` - Technical Architecture
System architecture, data workflows, and integration patterns:

**Core Architecture:**
- **`storage-manager-abstraction.md`** - Multi-driver storage system (local/S3/remote with PHI compliance)
- **`upload-submission-workflow.md`** - Multi-file submission workflow (patient-first validation, versioning)

**Streaming & Integration:**
- `file_streaming_architecture.md` - File streaming between web and services servers
- `development_streaming_setup.md` - Development environment streaming configuration
- `quick_start_streaming.md` - Quick setup for streaming architecture
- `two-server-streaming-setup.md` - Production two-server streaming setup

**Data Systems:**
- `patient-id-validation-system.md` - Cross-file patient ID validation system
- `nas_configuration.md` - NAS storage configuration and setup
- `database-refresh.md` - Database refresh and migration procedures
- `implementation_steps.md` - Implementation planning and steps

### `/testing/` - Testing & Quality Assurance
Testing frameworks, procedures, and quality assurance:

- `testing-audit-system.md` - Audit system testing procedures and validation
- `test-server-setup.md` - Test server configuration and setup

### `/user/` - User Documentation
End-user guides and workflows:

- `README.md` - User documentation overview
- `creating-submission.md` - Creating multi-file submissions
- `uploading-data-files.md` - File upload procedures
- `managing-submissions.md` - Submission management workflows
- `managing-data-tables.md` - Data table management

### `/worklogs/` - Development Logs
Development session logs and implementation tracking:

- Chronological development worklog entries
- Implementation details and debugging sessions
- Progress tracking for complex features

### `/archive/` - Historical Documentation
Archived/superseded documentation kept for reference:

- `deployment-guide-complete.md` - Superseded by `production.md`
- `phi-compliant-deployment.md` - Merged into `production.md`
- `dev-setup-complete.md` - Superseded by `development.md`
- `ansible-deployment.md` - Consolidated into `ansible.md`
- `ansible-deployment-guide.md` - Consolidated into `ansible.md`
- `local-ansible-deployment.md` - Merged into `ansible.md`
- `container-build-improvements.md` - Historical container changes
- `container-optimization-status.md` - Point-in-time status report

## 🎯 Quick Start Guide

### For Developers
1. **Local Development Setup**: Start with [`/deployment/development.md`](deployment/development.md)
2. **Architecture Overview**: Read [`/technical/storage-manager-abstraction.md`](technical/storage-manager-abstraction.md) and [`/technical/upload-submission-workflow.md`](technical/upload-submission-workflow.md)
3. **Security Patterns**: Review [`/security/PHIFileTracking-system.md`](security/PHIFileTracking-system.md)

### For Deployment
1. **Production Deployment**: Follow [`/deployment/production.md`](deployment/production.md)
2. **Ansible Automation**: Use [`/deployment/ansible.md`](deployment/ansible.md)
3. **Container Builds**: See [`/deployment/containers/docker.md`](deployment/containers/docker.md)
4. **Security Configuration**: Implement [`/security/wireguard.md`](security/wireguard.md) for PHI encryption

### For Testing
1. **Testing Setup**: Use [`/testing/test-server-setup.md`](testing/test-server-setup.md)
2. **Authentication Testing**: Follow [`/security/saml-testing.md`](security/saml-testing.md)
3. **System Validation**: Use [`/testing/testing-audit-system.md`](testing/testing-audit-system.md)

## 🏗️ Architecture Overview

NA-ACCORD uses a sophisticated **two-server PHI-compliant architecture**:

```
Web Server (10.150.96.6)       Services Server (10.150.96.37)
┌─────────────────────┐        ┌─────────────────────────┐
│ - Public access     │        │ - PHI data processing   │
│ - Authentication    │ ────── │ - File storage (NAS)    │
│ - File streaming    │        │ - R analysis + Quarto   │
│ - No PHI storage    │        │ - Database (encrypted)  │
└─────────────────────┘        └─────────────────────────┘
         │                                  │
         └─── WireGuard Encrypted Tunnel ──┘
           ChaCha20-Poly1305 (HIPAA-compliant)
```

**Key Features:**
- **PHI Isolation**: Web server never stores PHI data locally
- **Multi-Driver Storage**: NAS network storage with driver architecture supporting future S3-compatible migration
- **Comprehensive Audit**: Complete PHI file tracking for HIPAA compliance
- **Encrypted Transit**: WireGuard VPN for all PHI data transfer
- **R Integration**: Statistical validation using NAATools package and Quarto reports
- **Container Orchestration**: Docker-based deployment with multi-stage optimization

## 📚 Related Documentation

### Domain-Specific CLAUDE.md Files
For enhanced AI assistance, subdomain-specific CLAUDE.md files provide targeted context:

- `../depot/upload_submissions/CLAUDE.md` - Upload submission workflow patterns
- `../depot/security/CLAUDE.md` - PHI compliance and security patterns
- `../depot/storage/CLAUDE.md` - Storage architecture and abstraction
- `../depot/audit/CLAUDE.md` - Data validation and R integration workflow
- `../deploy/CLAUDE.md` - Container orchestration and deployment patterns
- `CLAUDE.md` - **This documentation domain context**

### Main Project Documentation
- `../CLAUDE.md` - **Main development guide** with comprehensive architecture details
- `../README.md` - Project overview and getting started

## 🔄 Documentation Maintenance

This documentation was comprehensively reorganized in September 2025 to:

1. **Eliminate Redundancy**: Consolidated 3 Ansible guides into 1, merged 3 production deployment guides
2. **Improve Organization**:
   - Moved all security docs from `deploy/` to `security/`
   - Created `deployment/containers/` subdirectory for container docs
   - Created `deployment/tools/` for development tools
   - Created `archive/` for superseded documentation
3. **Enhance Clarity**: Single source of truth for each topic (production, development, Ansible)
4. **Add Missing Coverage**: Comprehensive PHI tracking, storage abstraction, upload workflow documentation
5. **Support AI Assistance**: Domain-specific CLAUDE.md files for targeted context

### Current Structure
```
docs/
├── deployment/          # Production & development deployment
│   ├── production.md   # Primary production guide
│   ├── development.md  # Primary development guide
│   ├── ansible.md      # Consolidated Ansible guide
│   ├── containers/     # Container-specific docs
│   └── tools/          # Deployment tooling
├── security/           # Security & compliance
│   ├── wireguard.md    # VPN implementation
│   ├── api-keys.md     # Key rotation
│   └── logging/        # Compliance logging
├── technical/          # Architecture & workflows
├── testing/            # QA procedures
├── user/               # End-user guides
└── archive/            # Superseded documentation
```

### File Organization Principles

- **Primary Files**: Current, authoritative guides (e.g., `production.md`, `ansible.md`)
- **Archived Files**: Historical documentation in `/archive/` for reference
- **Subdirectories**: Logical grouping by function (containers, tools, logging)
- **Clear Naming**: Descriptive filenames without version numbers or dates
- **Cross-References**: Links between related documentation maintained during updates

For documentation updates, please maintain this organizational structure and update both the specific documentation and this README as needed.