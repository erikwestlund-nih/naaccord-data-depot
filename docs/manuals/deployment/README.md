# NA-ACCORD Deployment Documentation

**Last Updated:** 2025-10-04
**Deployment Method:** Ansible-based infrastructure automation
**Target Environments:** Staging (local VMs) + Production (JHU servers)

## 🚨 Recent Critical Updates

**2025-10-04 - WireGuard Tunnel Configuration Fix**
- Fixed network subnet conflicts (10.100.0.0/24 vs 10.101.0.0/24)
- Corrected WireGuard public key generation (must derive from private keys)
- Added automatic iptables port forwarding
- **See:** [WireGuard Tunnel Fix](wireguard-tunnel-fix.md) for complete details

## Quick Links

- **[Architecture Overview](guides/architecture.md)** - Two-server PHI-compliant design
- **[Deployment Workflow](guides/deployment-workflow.md)** - How to deploy
- **[WireGuard Tunnel Fix](wireguard-tunnel-fix.md)** - ⭐ Critical tunnel configuration (2025-10-04)
- **[WireGuard Keys Guide](guides/wireguard-keys.md)** - Key generation for Ansible
- **[Emergency Access](guides/emergency-access.md)** - IT emergency procedures

**Implementation Tracking:**
- **[Deploy TODO Tracking](../deploy-todo-tracking.md)** - Phase-by-phase checklist

## Deployment Philosophy

### Key Principles
1. **Infrastructure as Code**: All configuration managed through Ansible
2. **SAML-Only Authentication**: No password-based login
3. **PHI Compliance**: Two-server isolation with encrypted tunnels
4. **Simplicity Over Complexity**: Pragmatic choices for small team operations
5. **Encryption Everywhere**: Database, Redis volumes, WireGuard tunnels

### Architecture Decisions

Based on multi-model consensus analysis (see ../deploy-todo-tracking.md):

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Container Registry | GHCR | GitHub-integrated, zero additional infra |
| SSL/TLS | Let's Encrypt DNS-01 | No port 80 exposure, Cloudflare automation |
| Emergency Access | IT via Django shell | Secure, auditable, documented |
| Redis Persistence | Basic RDB (60s) | Survives restarts, no complex monitoring |
| Backups | MariaDB to NAS | Simple, focused on critical data only |
| Logging | Loki + Grafana | Lightweight centralized, automatic rotation |
| Migrations | Ansible-controlled | Safe, explicit, part of deploy workflow |
| Static Files | Build locally, commit | Simple workflow, no CI/CD complexity |
| Celery Workers | 1 per core, autoscale | Conservative start, monitor and adjust |
| Monitoring | Grafana + Slack alerts | Web-hosted, security-conscious metrics |

## Documentation Structure

```
docs/deployment/
├── README.md                     # This file
├── guides/
│   ├── architecture.md           # System architecture overview
│   ├── deployment-workflow.md    # Step-by-step deployment process
│   ├── ansible-roles.md          # Ansible role reference
│   └── emergency-access.md       # IT emergency procedures
└── reference/
    └── environments.md           # Environment-specific details
```

## Getting Started

### For Initial Deployment

1. Read [Architecture Overview](guides/architecture.md) to understand the system
2. Follow [Deployment Workflow](guides/deployment-workflow.md) step-by-step
3. Track progress in [Deploy TODO](../deploy-todo-tracking.md)

### For Updates/Maintenance

1. Use the `deploy` Ansible role (see [Ansible Roles](guides/ansible-roles.md))
2. Follow deployment workflow for tested updates
3. Monitor through Grafana dashboards

### For Emergency Access

See [Emergency Access Guide](guides/emergency-access.md) for IT procedures

## Support

- **Implementation Tracking**: See `docs/deploy-todo-tracking.md`
- **Ansible Code**: See `deploy/ansible/` (after Phase 0 archive)
- **Container Definitions**: See `deploy/containers/` or Dockerfiles in root
- **Main Documentation**: See `/docs/CLAUDE.md` for overall project context
