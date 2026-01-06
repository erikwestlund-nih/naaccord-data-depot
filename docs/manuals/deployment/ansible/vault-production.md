# Production Vault Management

## ⚠️ CRITICAL: Production Vault Security

The staging vault uses password `changeme` - **THIS MUST NEVER BE USED IN PRODUCTION**.

## Production Deployment Checklist

### 1. Change Production Vault Password

**BEFORE deploying to production servers:**

```bash
# Navigate to ansible directory
cd /opt/naaccord/depot/deploy/ansible

# Re-key the production vault with a strong password
ansible-vault rekey inventories/production/group_vars/vault.yml

# You will be prompted:
# - Current password: changeme
# - New password: <STRONG_PASSWORD_HERE>
# - Confirm new password: <STRONG_PASSWORD_HERE>
```

**Password Requirements:**
- Minimum 20 characters
- Mix of uppercase, lowercase, numbers, symbols
- Generated using password manager (LastPass, 1Password, etc.)
- NOT derived from dictionary words or patterns
- DIFFERENT from staging password

### 2. Update Production Vault with JHU IT Credentials

Once you have the NAS credentials from JHU IT:

```bash
# Edit production vault
ansible-vault edit inventories/production/group_vars/vault.yml
# Enter the NEW vault password

# Update the contents:
---
# Production secrets
nas_username: "actual_username_from_jhu"
nas_password: "actual_password_from_jhu"
```

### 3. Update Production Inventory NAS Details

Edit `inventories/production/hosts.yml` and replace TBD values:

```yaml
vars:
  environment: production
  domain: mrpznaaccordweb01.hosts.jhmi.edu
  nas_host: "10.150.96.XX"  # Actual NAS IP from JHU IT
  nas_share: "naaccord_submissions"  # Actual share name from JHU IT
```

### 4. Secure Vault Password Storage

**DO NOT:**
- ❌ Store password in git
- ❌ Store password in plain text files
- ❌ Email password
- ❌ Share password in Slack/Teams
- ❌ Write password on paper or whiteboard
- ❌ Use same password for staging and production

**DO:**
- ✅ Store in enterprise password manager (LastPass, 1Password, etc.)
- ✅ Share via password manager's secure sharing feature
- ✅ Limit access to deployment team only
- ✅ Use different passwords for staging vs production
- ✅ Rotate password periodically (every 90 days)

### 5. Production Deployment Usage

**Option A: Interactive (Recommended for Manual Deploys)**
```bash
ansible-playbook -i inventories/production/hosts.yml \
  playbooks/services-server.yml \
  --ask-vault-pass
# You will be prompted to enter vault password
```

**Option B: Password File (CI/CD Only)**
```bash
# ONLY for automated CI/CD pipelines with proper secret management
ansible-playbook -i inventories/production/hosts.yml \
  playbooks/services-server.yml \
  --vault-password-file /path/to/secure/password/file
```

⚠️ **Never commit password files to git!**

**Option C: Environment Variable (CI/CD)**
```bash
# Set in CI/CD secrets (GitHub Actions, Jenkins, etc.)
export ANSIBLE_VAULT_PASSWORD="<password_from_secret_manager>"

ansible-playbook -i inventories/production/hosts.yml \
  playbooks/services-server.yml \
  --vault-password-file <(echo "$ANSIBLE_VAULT_PASSWORD")
```

## Who Needs Access

**Vault Password Access:**
- Deployment team (2-3 people maximum)
- Senior infrastructure engineer
- Backup: One team lead for emergencies

**DO NOT share with:**
- Developers (unless they are deployment engineers)
- Contractors without proper clearance
- External parties
- Service accounts (use dedicated secret management instead)

## Credential Rotation Procedure

**Every 90 days or when personnel change:**

1. Get new NAS credentials from JHU IT
2. Update vault:
   ```bash
   ansible-vault edit inventories/production/group_vars/vault.yml
   ```
3. Test with dry-run:
   ```bash
   ansible-playbook -i inventories/production/hosts.yml \
     playbooks/services-server.yml \
     --check --ask-vault-pass
   ```
4. Deploy during maintenance window

**After personnel leave:**
1. Immediately rekey vault with new password
2. Notify JHU IT to rotate NAS credentials
3. Update vault with new NAS credentials
4. Document access revocation

## Emergency Access

If vault password is lost:

1. **DO NOT PANIC** - vault can be recreated
2. Contact JHU IT for new NAS credentials
3. Create new vault file:
   ```bash
   # Backup old vault (you can't decrypt it, but keep for records)
   mv inventories/production/group_vars/vault.yml \
      inventories/production/group_vars/vault.yml.lost

   # Create new vault with new password
   ansible-vault create inventories/production/group_vars/vault.yml
   ```
4. Add new NAS credentials from JHU IT
5. Document incident

## Verification Commands

**Check vault is encrypted:**
```bash
file inventories/production/group_vars/vault.yml
# Should output: ASCII text (indicating encrypted vault format)

head -1 inventories/production/group_vars/vault.yml
# Should output: $ANSIBLE_VAULT;1.1;AES256
```

**Verify vault contents (without editing):**
```bash
ansible-vault view inventories/production/group_vars/vault.yml
# Enter password when prompted
```

**Test vault password without running playbook:**
```bash
ansible-vault view inventories/production/group_vars/vault.yml --ask-vault-pass
```

## Integration with JHU IT

**Before production deployment, coordinate with JHU IT for:**

1. **NAS Access Credentials**
   - Username for CIFS/SMB mount
   - Password for authentication
   - Confirm credential rotation policy

2. **NAS Network Details**
   - NAS server IP address or hostname
   - SMB share name
   - Network path (//server/share)
   - Firewall rules (if needed)

3. **Access Permissions**
   - Verify services server (10.150.96.37) can reach NAS
   - Test connectivity before Ansible deployment
   - Confirm read/write permissions

4. **Compliance Requirements**
   - Ensure NAS meets HIPAA requirements
   - Verify encryption at rest
   - Confirm backup procedures
   - Audit logging requirements

## Security Best Practices

1. **Principle of Least Privilege**
   - Only deployment engineers need vault password
   - Grant access on as-needed basis
   - Revoke immediately when role changes

2. **Defense in Depth**
   - Vault password protects credentials
   - NAS credentials provide second layer
   - Server access requires VPN + SSH keys
   - Root access requires sudo password

3. **Audit Trail**
   - Log all vault access attempts
   - Document who deployed when
   - Track credential rotation dates
   - Maintain access control list

4. **Regular Review**
   - Quarterly access review
   - Annual security audit
   - Test emergency procedures
   - Update documentation

## Troubleshooting

**"ERROR! Vault password incorrect"**
- Verify you're using production password (not staging "changeme")
- Check password manager for correct entry
- Verify no extra spaces or characters
- Try `ansible-vault view` to test password

**"ERROR! vault.yml not found"**
- Verify you're in correct directory
- Check inventory path is correct
- Ensure file wasn't accidentally deleted

**"WARNING! Using world-readable password file"**
- Password file permissions must be 0600
- `chmod 600 /path/to/password/file`
- Better: use --ask-vault-pass instead

**NAS mount fails after vault update**
- Verify credentials with JHU IT
- Test manual mount to confirm credentials
- Check network connectivity to NAS
- Review firewall rules

## Related Documentation

- [../docs/deployment/guides/emergency-access.md](../../docs/deployment/guides/emergency-access.md) - Emergency access procedures
- [deploy-steps.md](../deploy-steps.md) - Deployment workflow
- [roles/nas_mount/README.md](roles/nas_mount/README.md) - NAS mount configuration
