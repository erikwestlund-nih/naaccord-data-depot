# Documentation Domain - CLAUDE.md

## Domain Overview

The documentation domain encompasses all user-facing documentation, technical guides, deployment instructions, and developer resources for NA-ACCORD. This domain maintains comprehensive documentation for the sophisticated PHI-compliant clinical research data platform, ensuring accuracy, organization, and accessibility.

## Documentation Architecture

### Directory Structure

```
docs/
├── CLAUDE.md                    # This file - AI assistant context
├── README.md                    # Navigation guide and quick start
├── deployment/                  # Deployment & infrastructure guides
├── technical/                   # System architecture & workflows
├── security/                    # PHI compliance & authentication
├── testing/                     # QA procedures & testing guides
├── user/                        # End-user documentation
├── worklogs/                    # Development session logs
└── deploy/                      # Infrastructure as code configs
```

### Documentation Types

**Primary Guides** (authoritative, current):
- `deployment/production-deployment.md` - Comprehensive production setup
- `deployment/development-setup.md` - Complete local development guide
- `technical/storage-manager-abstraction.md` - Multi-driver storage system
- `technical/upload-submission-workflow.md` - Multi-file submission workflow
- `security/PHIFileTracking-system.md` - HIPAA audit trail system

**Legacy/Reference Files** (historical, kept for completeness):
- Multiple deployment guides consolidated into primary guides
- Original implementation documentation preserved for reference
- Development logs and implementation notes in worklogs/

## Documentation Maintenance Patterns

### File Organization Principles

1. **Logical Grouping**: Files organized by functional domain
2. **Primary vs Legacy**: Clear distinction between current and historical docs
3. **Cross-References**: Links between related documentation
4. **Comprehensive Coverage**: Every major system documented
5. **AI-Friendly Structure**: Domain-specific CLAUDE.md files for specialized context

### Content Standards

**Technical Documentation**:
- Code examples with proper syntax highlighting
- Architecture diagrams using ASCII art
- Security considerations highlighted
- Performance implications noted
- Cross-references to related systems

**Deployment Documentation**:
- Step-by-step procedures
- Environment-specific configurations
- Security requirements
- Troubleshooting sections
- Health check procedures

**User Documentation**:
- Clear workflow descriptions
- Screenshot references where helpful
- Common scenarios covered
- Error handling guidance

### Writing Patterns

#### Documentation Headers
```markdown
# System Name - Purpose

## Overview
Brief description of what this system does and why it matters

## Architecture
Technical architecture with diagrams

## Key Features
- Bullet points of main capabilities
- Integration points
- Security considerations

## Implementation
Code examples and configuration patterns

## Related Documentation
Links to related files
```

#### Code Documentation
```python
# GOOD: Include context and security notes
def save_phi_file(file_path, content, user, cohort):
    """
    Save PHI file with complete audit trail

    SECURITY: This function handles PHI data and must:
    - Log all operations for HIPAA compliance
    - Validate user permissions
    - Track file cleanup requirements
    """
    # Implementation with security patterns
```

#### Configuration Examples
```bash
# Production configuration (secure)
SERVER_ROLE=web
INTERNAL_API_KEY=secure-production-key
SERVICES_URL=https://services.naaccord.internal:8001

# Development configuration (local)
SERVER_ROLE=testing
SCRATCH_STORAGE_DISK=local
```

## Key Documentation Systems

### Deployment Documentation

**Primary Files**:
- `deployment/production-deployment.md` - Complete HIPAA-compliant production setup
- `deployment/development-setup.md` - Local development with tmux management

**Coverage Areas**:
- Two-server architecture setup
- Container orchestration with Docker
- Ansible automation playbooks
- Security configuration (WireGuard, SSL)
- Database setup and optimization
- Monitoring and health checks

### Technical Architecture Documentation

**Core Systems**:
- `technical/storage-manager-abstraction.md` - Multi-driver storage system (NAS with future S3 support)
- `technical/upload-submission-workflow.md` - Multi-file submission with validation
- `technical/wireguard-architecture.md` - Network security architecture

**Architecture Patterns**:
- PHI-compliant two-server design
- Storage abstraction (NAS/remote with future S3 support)
- File streaming between servers
- Patient-first validation workflow
- Cross-file integrity checking

### Security Documentation

**Primary Files**:
- `security/PHIFileTracking-system.md` - Comprehensive HIPAA audit system
- `security/auth-workflow.md` - Authentication and SAML integration
- `security/saml-testing.md` - Authentication testing procedures

**Security Patterns**:
- PHI isolation between servers
- Complete audit trail for all file operations
- Role-based access control
- Encrypted inter-server communication
- Compliance verification procedures

## Documentation Relationships

### Integration with Code

```python
# Documentation references in code comments
class PHIFileTracking(models.Model):
    """
    HIPAA-compliant audit trail for all PHI file operations.

    See: docs/security/PHIFileTracking-system.md
    """

def get_storage_driver(self):
    """
    Multi-driver storage selection based on server role.

    See: docs/technical/storage-manager-abstraction.md
    """
```

### Cross-Domain References

**From Code to Docs**:
- Code comments reference relevant documentation
- Management commands include help text pointing to guides
- Error messages include documentation links

**From Docs to Code**:
- Documentation includes file paths for implementation
- Code examples show actual usage patterns
- Configuration examples match production settings

### Domain-Specific CLAUDE.md Integration

The main docs work in conjunction with specialized domain CLAUDE.md files:

- `../depot/upload_submissions/CLAUDE.md` - Submission workflow implementation
- `../depot/security/CLAUDE.md` - Security patterns and PHI compliance
- `../depot/storage/CLAUDE.md` - Storage architecture implementation
- `../depot/audit/CLAUDE.md` - Audit workflow and R integration
- `../deploy/CLAUDE.md` - Container orchestration and deployment

## Common Operations

### Adding New Documentation

```bash
# 1. Determine appropriate subdirectory
# deployment/ - Setup and infrastructure
# technical/ - Architecture and workflows
# security/ - PHI compliance and auth
# testing/ - QA and validation
# user/ - End-user guides

# 2. Create file with standard header
# 3. Add cross-references to related docs
# 4. Update README.md navigation if major addition
```

### Updating Existing Documentation

```bash
# 1. Verify accuracy against current codebase
# 2. Update code examples to match current patterns
# 3. Check all cross-references still valid
# 4. Update modification date in content
```

### Documentation Review Process

1. **Accuracy Check**: Verify against current codebase implementation
2. **Security Review**: Ensure PHI compliance patterns documented
3. **Completeness**: Check all major features covered
4. **Organization**: Confirm proper directory placement
5. **Cross-References**: Validate all links and references

## Documentation Workflows

### For New Features

```python
# When implementing new features, always update:
# 1. Relevant technical documentation
# 2. Deployment guides if configuration changes
# 3. Security documentation if PHI handling involved
# 4. User documentation if workflow changes
# 5. Domain-specific CLAUDE.md files

def implement_new_feature():
    """
    New feature implementation workflow:

    1. Code implementation
    2. Update technical/[relevant-system].md
    3. Update deployment docs if needed
    4. Update security docs if PHI involved
    5. Update domain CLAUDE.md file
    """
```

### For Bug Fixes

```python
def document_bug_fix():
    """
    Bug fix documentation workflow:

    1. Add to worklogs/ with details
    2. Update relevant troubleshooting sections
    3. Update configuration examples if needed
    4. Note security implications if any
    """
```

### For Configuration Changes

```bash
# Configuration change documentation:
# 1. Update deployment guides
# 2. Update environment variable documentation
# 3. Update security configuration if applicable
# 4. Update container configurations
# 5. Update health check procedures
```

## Quality Standards

### Technical Accuracy

- All code examples must be tested and functional
- Configuration examples must match production patterns
- Architecture diagrams must reflect current implementation
- Security patterns must be HIPAA-compliant

### Accessibility

- Clear navigation structure
- Comprehensive README for getting started
- Cross-references between related topics
- Quick start guides for common workflows

### Maintainability

- Regular review for accuracy
- Version control for all changes
- Clear distinction between current and legacy
- Standardized file naming and organization

## Troubleshooting Documentation Issues

### Common Problems

**Outdated Information**:
- Regular review against codebase changes
- Update configuration examples
- Verify deployment procedures

**Missing Cross-References**:
- Check related documentation links
- Update README navigation
- Verify domain CLAUDE.md references

**Organizational Issues**:
- Files in wrong subdirectories
- Duplicate information across files
- Unclear primary vs legacy distinction

### Maintenance Procedures

```bash
# Monthly documentation review
# 1. Check all code examples for accuracy
# 2. Verify deployment procedures
# 3. Update configuration examples
# 4. Review security documentation for compliance
# 5. Check cross-references and links

# After major releases
# 1. Update all relevant technical documentation
# 2. Review deployment guides for changes
# 3. Update user workflows if modified
# 4. Verify security patterns still documented
```

## Related Resources

### Main Project Documentation
- `../CLAUDE.md` - Main development guide with architecture overview
- `../README.md` - Project overview and getting started

### Domain-Specific Context
- `../depot/*/CLAUDE.md` - Implementation-specific AI assistance
- `../deploy/CLAUDE.md` - Deployment and infrastructure patterns

### External References
- NA-ACCORD project requirements
- HIPAA compliance guidelines
- Security best practices documentation
- Clinical research data standards

This documentation domain ensures comprehensive, accurate, and well-organized information for the sophisticated NA-ACCORD clinical research platform, supporting both human users and AI assistance in understanding and maintaining the system.