# SSL Certificate Installation - Production

## Overview
NA-ACCORD production requires IT-provided SSL certificates for HTTPS on port 443.

**Important:** Staging uses Nginx Proxy Manager for SSL - these placeholders are **production only**.

## Certificate Requirements

### Files Needed from JHU IT
1. **Server Certificate** (`server.crt.placeholder`)
2. **Private Key** (`server.key.placeholder`)
3. **CA Bundle/Chain** (`ca-bundle.crt.placeholder`)

### Certificate Specifications
- **Common Name (CN):** `mrpznaaccordweb01.hosts.jhmi.edu`
- **Subject Alternative Names (SANs):**
  - `mrpznaaccordweb01.hosts.jhmi.edu`
  - (Optional: add any additional hostnames)
- **Valid Period:** Minimum 1 year
- **Key Type:** RSA 2048-bit or higher (or ECDSA P-256)
- **Signed By:** JHU-trusted Certificate Authority
- **Format:** PEM encoded
- **Chain:** Must include intermediate CA certificates

## Installation Paths on Production Server

The Ansible playbook expects certificates at these exact paths:

```bash
/etc/ssl/certs/naaccord/server.crt       # Server certificate
/etc/ssl/private/naaccord/server.key     # Private key (600 permissions)
/etc/ssl/certs/naaccord/ca-bundle.crt    # CA chain
```

## Installation Steps for JHU IT

### 1. Create Directory Structure
```bash
# On production web server (10.150.96.6)
sudo mkdir -p /etc/ssl/certs/naaccord
sudo mkdir -p /etc/ssl/private/naaccord
```

### 2. Copy Certificate Files
```bash
# Copy certificate (readable by all)
sudo cp /path/to/certificate.crt /etc/ssl/certs/naaccord/server.crt
sudo chmod 644 /etc/ssl/certs/naaccord/server.crt

# Copy private key (root only!)
sudo cp /path/to/private.key /etc/ssl/private/naaccord/server.key
sudo chmod 600 /etc/ssl/private/naaccord/server.key
sudo chown root:root /etc/ssl/private/naaccord/server.key

# Copy CA bundle (readable by all)
sudo cp /path/to/ca-bundle.crt /etc/ssl/certs/naaccord/ca-bundle.crt
sudo chmod 644 /etc/ssl/certs/naaccord/ca-bundle.crt
```

### 3. Verify Certificate Files
```bash
# Check certificate details
openssl x509 -in /etc/ssl/certs/naaccord/server.crt -noout -text

# Verify certificate matches private key
openssl x509 -noout -modulus -in /etc/ssl/certs/naaccord/server.crt | openssl md5
openssl rsa -noout -modulus -in /etc/ssl/private/naaccord/server.key | openssl md5
# ^ These two MD5 hashes must match!

# Check certificate expiry
openssl x509 -in /etc/ssl/certs/naaccord/server.crt -noout -dates

# Verify certificate chain
openssl verify -CAfile /etc/ssl/certs/naaccord/ca-bundle.crt /etc/ssl/certs/naaccord/server.crt
```

### 4. Test with Ansible
```bash
# Dry run to verify files are readable
ansible-playbook -i inventories/production/hosts.yml \
  playbooks/web-server.yml \
  --tags ssl \
  --check

# Apply SSL configuration
ansible-playbook -i inventories/production/hosts.yml \
  playbooks/web-server.yml \
  --tags ssl
```

## Architecture Overview

### Staging (Current - Pequod Network)
```
Internet → NPM (70.22.166.28:443) → 192.168.50.10:80
         ↑ SSL Termination Here
```
- Nginx Proxy Manager handles SSL
- Let's Encrypt certificates via NPM
- Backend accepts HTTP only on port 80
- **No certificates needed on staging server**

### Production (JHU Network)
```
Internet → JHU Firewall → 10.150.96.6:443 (Web Server)
                                    ↑ SSL Termination Here
```
- Web server handles SSL directly
- IT-provided certificates from JHU CA
- Direct HTTPS on port 443
- **Certificates required on web server**

## Troubleshooting

### Certificate Not Found Error
```
Error: SSL Certificate files not found on server!
Missing file: /etc/ssl/certs/naaccord/server.crt
```

**Solution:** Verify files exist at exact paths above

### Permission Denied Error
```
Error: nginx: [emerg] BIO_new_file("/etc/ssl/private/naaccord/server.key") failed
```

**Solution:** Check private key permissions (should be 600, owned by root)

### Certificate Chain Invalid
```
Error: SSL certificate verify failed
```

**Solution:** Ensure ca-bundle.crt contains complete chain (intermediate + root CA)

### SELinux Denials (if enabled)
```bash
# Check for denials
sudo ausearch -m avc -ts recent

# Allow nginx to read certificates
sudo semanage fcontext -a -t cert_t "/etc/ssl/certs/naaccord(/.*)?"
sudo semanage fcontext -a -t cert_t "/etc/ssl/private/naaccord(/.*)?"
sudo restorecon -R /etc/ssl/certs/naaccord
sudo restorecon -R /etc/ssl/private/naaccord
```

## Certificate Renewal Process

### When to Renew
- 30 days before expiration (automated alerts recommended)
- Certificate expiry monitoring via Grafana/Nagios

### Renewal Steps
1. Obtain new certificate from JHU IT
2. Back up old certificate:
   ```bash
   sudo cp /etc/ssl/certs/naaccord/server.crt /etc/ssl/certs/naaccord/server.crt.bak-$(date +%Y%m%d)
   ```
3. Install new certificate (same paths as above)
4. Restart nginx:
   ```bash
   sudo docker restart naaccord-nginx
   ```
5. Verify new certificate:
   ```bash
   openssl s_client -connect mrpznaaccordweb01.hosts.jhmi.edu:443 -servername mrpznaaccordweb01.hosts.jhmi.edu < /dev/null 2>/dev/null | openssl x509 -noout -dates
   ```

## Security Notes

- **Private key must NEVER leave the server**
- Private key permissions MUST be 600 (root read/write only)
- Certificate files should be backed up securely
- No private keys in git repository (ever!)
- Use placeholder files to document paths only

## Contact Information

**For certificate requests:**
- JHU IT Service Desk
- Certificate Authority team
- Provide: Server hostname, CSR (if required), expiration date needed

**For technical issues:**
- NA-ACCORD system administrator
- Refer to: `deploy/ansible/roles/ssl/tasks/manual_certs.yml`
