# NA-ACCORD Deployment Instructions
**Date:** 2025-09-26
**Version:** 1.0

## Repository Information

### New GitHub Locations
- **Main Application:** https://github.com/JHBiostatCenter/naaccord-data-depot
- **R Package (NAATools):** https://github.com/JHBiostatCenter/naaccord-r-tools

### Cloning Repositories
```bash
# Clone main application
git clone https://github.com/JHBiostatCenter/naaccord-data-depot.git naaccord

# Clone R package (for development)
git clone https://github.com/JHBiostatCenter/naaccord-r-tools.git NAATools
```

## Container Status

| Container | Status | Image Size | Notes |
|-----------|--------|------------|-------|
| **naaccord/services:latest** | ✅ Built | ~2GB | Django, Celery, R, Quarto, NAATools |
| **naaccord/nginx:latest** | ✅ Built | 55.8MB | mTLS support, self-signed certs |
| **redis:7-alpine** | Public | 30MB | Use official image |

## Deployment Architecture

### Two-Server Setup
- **Web Server (192.168.50.10):** Nginx only, no PHI storage
- **Services Server (192.168.50.11):** Django, Celery, Redis, MariaDB (host-installed)

### Key Features
- ✅ MariaDB encryption at rest (direct installation)
- ✅ mTLS for inter-server communication
- ✅ Ansible-based reproducible deployment
- ✅ Local execution to avoid 2FA SSH issues

## Quick Deployment Steps

### 1. Push to New Repository
```bash
# Add new remote (if not done)
git remote set-url origin https://github.com/JHBiostatCenter/naaccord-data-depot.git

# Push all branches and tags
git push origin --all
git push origin --tags
```

### 2. Transfer Containers to Servers
```bash
# Save containers
docker save naaccord/services:latest | gzip > naaccord-services.tar.gz
docker save naaccord/nginx:latest | gzip > naaccord-nginx.tar.gz

# Transfer to servers
scp naaccord-services.tar.gz naaccord-services.lan:/tmp/
scp naaccord-nginx.tar.gz naaccord-web.lan:/tmp/
```

### 3. Deploy Services Server
```bash
ssh naaccord-services.lan

# Clone repository
git clone https://github.com/JHBiostatCenter/naaccord-data-depot.git /opt/naaccord
cd /opt/naaccord

# Load container
docker load < /tmp/naaccord-services.tar.gz

# Set up vault password
echo "your-vault-password" > /tmp/vault-pass

# Run Ansible deployment
cd ansible
ansible-playbook \
  -i inventories/test/hosts.yml \
  playbooks/site.yml \
  --limit naaccord-services-test \
  --connection local \
  --vault-password-file /tmp/vault-pass

# Clean up
rm /tmp/vault-pass
```

### 4. Deploy Web Server
```bash
ssh naaccord-web.lan

# Clone repository
git clone https://github.com/JHBiostatCenter/naaccord-data-depot.git /opt/naaccord
cd /opt/naaccord

# Load container
docker load < /tmp/naaccord-nginx.tar.gz

# Run deployment
cd ansible
ansible-playbook \
  -i inventories/test/hosts.yml \
  playbooks/site.yml \
  --limit naaccord-web-test \
  --connection local \
  --vault-password-file /tmp/vault-pass
```

## Verification Steps

### Check MariaDB Encryption
```bash
# On services server
mysql -u root -p -e "SHOW VARIABLES LIKE 'innodb_encrypt%';"

# Should show:
# innodb_encrypt_tables = ON
# innodb_encrypt_log = ON
```

### Check Services
```bash
# Services server
docker ps --format "table {{.Names}}\t{{.Status}}"
curl http://localhost:8000/health/

# Web server
curl -k https://localhost/health
```

## Important Files

### Ansible Playbooks
- `ansible/playbooks/site.yml` - Master playbook
- `ansible/playbooks/tasks/setup-mariadb-encryption.yml` - MariaDB encryption
- `ansible/playbooks/tasks/deploy-services.yml` - Services deployment

### Configuration
- `ansible/vars/vault.yml` - Encrypted secrets (create from vault.yml.example)
- `ansible/vars/services.yml` - Service configuration
- `.env.deploy.example` - Environment variables template

### Documentation
- `ansible/README-DEPLOYMENT.md` - Complete Ansible deployment guide
- `docs/deployment-checklist.md` - Deployment checklist

## Troubleshooting

### Container Build Issues
If you need to rebuild with new repository URLs:
```bash
# Update Dockerfile
sed -i 's|erikwestlund/naatools|JHBiostatCenter/naaccord-r-tools|g' deploy/containers/services/Dockerfile

# Rebuild
docker build -t naaccord/services:latest -f deploy/containers/services/Dockerfile .
```

### MariaDB Encryption Not Active
1. Check `/etc/mysql/encryption/` directory exists
2. Verify `/etc/my.cnf.d/encryption.cnf` exists
3. Restart MariaDB: `systemctl restart mariadb`

### R Package Installation
The container now installs NAATools from:
```r
remotes::install_github('JHBiostatCenter/naaccord-r-tools')
```

## Next Steps

1. ✅ Containers built and tested
2. ✅ Repository URLs updated
3. ✅ Ansible playbooks ready
4. ⏳ Push to new GitHub repositories
5. ⏳ Deploy to test servers (192.168.50.x)
6. ⏳ Verify MariaDB encryption
7. ⏳ Test complete workflow
8. ⏳ Deploy to production (10.150.96.x)

## Contact

- Repository: https://github.com/JHBiostatCenter/naaccord-data-depot
- R Package: https://github.com/JHBiostatCenter/naaccord-r-tools