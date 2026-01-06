# Test Server Deployment - 2025-09-26

## Objective
Deploy NA-ACCORD to test servers (192.168.50.10 and 192.168.50.11) using Ansible

## What You Need to Do

### Step 1: Push Code to GitHub

First, commit and push all our changes:

```bash
cd /Users/erikwestlund/code/naaccord
git add -A
git commit -m "Add Ansible deployment for MariaDB and complete deployment guides"
git push origin main
```

### Step 2: SSH into Services Server

```bash
ssh 192.168.50.11
```

### Step 3: On the Services Server - Initial Setup

```bash
# Install required packages
sudo dnf install -y git ansible python3-pip

# Create app directory
sudo mkdir -p /app
sudo chown $USER:$USER /app
cd /app

# Clone the repository (use correct name)
git clone https://github.com/JHBiostatCenter/naaccord-data-depot.git naaccord
cd naaccord
```

### Step 4: Create Ansible Vault Secrets

```bash
cd ansible

# Create secrets file with Ansible vault
ansible-vault create vars/secrets.yml
```

When prompted for vault password, use something secure and remember it.

Add this content to the file:
```yaml
---
# Generate random passwords or set your own
vault_mariadb_root_password: "GenerateSecurePassword32Chars"
vault_mariadb_app_password: "GenerateSecurePassword32Chars"
vault_mariadb_report_password: "GenerateSecurePassword32Chars"
vault_mariadb_backup_password: "GenerateSecurePassword32Chars"
vault_mariadb_encryption_key: "GenerateHex64CharsForEncryption"

vault_django_secret_key: "GenerateSecurePassword64Chars"
vault_redis_password: "GenerateSecurePassword32Chars"
vault_internal_api_key: "GenerateSecurePassword64Chars"
vault_flower_password: "GenerateSecurePassword32Chars"

# Your GitHub PAT for pulling containers
vault_github_token: "ghp_YourGitHubPersonalAccessToken"
```

To generate secure passwords on the server:
```bash
# Generate 32 char password
openssl rand -base64 32 | tr -d "=+/" | cut -c1-32

# Generate 64 char hex
openssl rand -hex 32

# Generate 64 char password
openssl rand -base64 64 | tr -d "=+/" | cut -c1-64
```

### Step 5: Run MariaDB Installation

```bash
# Make sure you're in /app/naaccord/ansible
cd /app/naaccord/ansible

# Run the MariaDB installation playbook locally
ansible-playbook -i inventories/test/hosts.yml \
    playbooks/install-mariadb.yml \
    --connection=local \
    --limit localhost \
    --ask-vault-pass
```

Enter your vault password when prompted.

### Step 6: Verify MariaDB Installation

After the playbook completes:

```bash
# Check MariaDB is running
sudo systemctl status mariadb

# Test connection (get password from ~/.env.deploy)
cat ~/.env.deploy | grep DB_APP_PASSWORD
mysql -u naaccord_app -p<password> naaccord -e "SELECT 1;"

# Verify encryption
sudo mysql -u root -p<root_password> -e "SELECT @@innodb_encrypt_tables;"
# Should return: 1
```

### Step 7: Load Container Images

You have three options:

#### Option A: Pull from GitHub Container Registry (if already pushed)
```bash
# Login to GitHub registry
docker login ghcr.io
# Username: your-github-username
# Password: your-github-PAT

# Pull images
docker pull ghcr.io/jhbiostatcenter/naaccord/services:latest
docker pull ghcr.io/jhbiostatcenter/naaccord/nginx:latest
```

#### Option B: Build locally on server
```bash
cd /app/naaccord
docker build -t naaccord/services:latest -f deploy/containers/services/Dockerfile .
docker build -t naaccord/nginx:latest -f deploy/containers/nginx/Dockerfile deploy/containers/nginx/
```

#### Option C: Transfer from your local machine
On your local machine:
```bash
docker save naaccord/services:latest | gzip > naaccord-services.tar.gz
docker save naaccord/nginx:latest | gzip > naaccord-nginx.tar.gz
scp naaccord-*.tar.gz 192.168.50.11:~/
```

On the server:
```bash
docker load < ~/naaccord-services.tar.gz
docker load < ~/naaccord-nginx.tar.gz
```

### Step 8: Start Services

```bash
cd /app/naaccord

# Copy environment file from home directory
cp ~/.env.deploy .env.deploy

# Start services with Docker
docker-compose -f docker-compose.yml up -d

# Check status
docker ps

# View logs
docker-compose -f docker-compose.yml logs -f
```

### Step 9: Initialize Django

```bash
# Run migrations
docker exec naaccord-django python manage.py migrate

# Create superuser
docker exec naaccord-django python manage.py createsuperuser

# Load initial data
docker exec naaccord-django python manage.py seed_init
docker exec naaccord-django python manage.py setup_permission_groups
```

### Step 10: Test Everything

```bash
# Test Django health
curl http://localhost:8000/health/

# Test Redis
docker exec naaccord-redis redis-cli ping

# Test Celery
docker exec naaccord-celery celery -A depot inspect active
```

## Web Server Setup (192.168.50.10)

After services server is working, SSH to web server and:

```bash
# Similar initial setup
sudo dnf install -y git ansible docker docker-compose
cd /app
git clone https://github.com/JHBiostatCenter/naaccord-data-depot.git naaccord
cd naaccord

# Pull or load nginx container
docker pull ghcr.io/jhbiostatcenter/naaccord/nginx:latest

# Configure nginx to point to services server
export UPSTREAM_HOST=192.168.50.11
export UPSTREAM_PORT=8000

# Start nginx
docker run -d \
    --name naaccord-nginx \
    -p 80:80 \
    -p 443:443 \
    -e UPSTREAM_HOST=$UPSTREAM_HOST \
    -e UPSTREAM_PORT=$UPSTREAM_PORT \
    naaccord/nginx:latest
```

## Verification from Your Machine

```bash
# Test web interface
curl -k https://192.168.50.10
# Should show login page

# Test API
curl https://192.168.50.10/api/health/
# Should return: {"status": "healthy"}
```

## If Something Goes Wrong

1. Check logs: `docker logs <container-name>`
2. Check `.env.deploy` has all required values
3. Verify MariaDB passwords match between database and Django config
4. Ensure containers can reach each other
5. For Docker, use `host.containers.internal` for database host

## Next Steps After This Works

1. Set up proper SSL certificates
2. Configure NAS mount
3. Set up monitoring
4. Configure backups
5. Document any customizations

---

## Notes

- Repository name: `naaccord-data-depot` (not just `naaccord`)
- Using Ansible for all configuration management
- Running Ansible locally on each server due to 2FA SSH restrictions
- MariaDB is native (not containerized) for production safety
- All secrets managed through Ansible Vault