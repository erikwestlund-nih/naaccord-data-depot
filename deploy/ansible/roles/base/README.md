# Base Role

Configures RHEL 8/Rocky Linux servers with essential packages, Docker, and a consistent shell environment for NA-ACCORD deployment.

## Requirements

- RHEL 8, Rocky Linux 8, or compatible
- Ansible 2.9+
- Root or sudo access

## Role Variables

See `defaults/main.yml` for all configurable variables.

### Key Variables

```yaml
# User management
base_create_naaccord_user: true
base_naaccord_uid: 1500
base_naaccord_gid: 1500

# System configuration
base_timezone: "America/New_York"
base_disable_selinux: true

# Docker configuration
base_docker_log_max_size: "10m"
base_docker_log_max_file: "3"
base_docker_storage_driver: "overlay2"
```

## Features

### Shell Environment
- Installs zsh for all users
- Configures oh-my-zsh with agnoster theme
- Sets up useful aliases and plugins
- Makes zsh the default shell

### Docker
- Installs Docker CE from official repository
- Configures log rotation
- Sets up overlay2 storage driver
- Adds naaccord user to docker group
- Enables Docker service

### Common Packages
- Development tools: git, curl, wget, vim, nano
- Monitoring tools: htop, ncdu, tree, iotop
- Python 3 with pip
- Storage tools: cifs-utils, nfs-utils
- Text processing: jq, yq
- Terminal multiplexers: tmux, screen

### System Configuration
- Sets timezone to America/New_York
- Configures hostname from inventory
- Disables SELinux (permissive mode)
- Configures kernel parameters for Docker
- Creates NA-ACCORD directory structure
- Sets up logrotate for application logs

### User Management
- Creates naaccord user (UID 1500) and group (GID 1500)
- Configures sudo access
- Sets proper directory permissions

## Directory Structure Created

```
/opt/naaccord/       # Application root
/var/log/naaccord/   # Application logs
/etc/naaccord/       # Configuration files
```

## Dependencies

None. This is a standalone base role.

## Example Playbook

```yaml
- hosts: all
  become: yes
  roles:
    - role: base
      vars:
        base_naaccord_uid: 1500
        base_naaccord_gid: 1500
```

## Tags

All tasks are tagged for selective execution:

- `base` - All base role tasks
- `users` - User and group management
- `packages` - Package installation
- `docker` - Docker installation
- `zsh` - Shell configuration
- `system` - System configuration

### Example Tag Usage

```bash
# Run only Docker installation
ansible-playbook site.yml --tags docker

# Run everything except zsh
ansible-playbook site.yml --skip-tags zsh

# Run only user and system configuration
ansible-playbook site.yml --tags users,system
```

## Testing

Test the role locally:

```bash
cd /opt/naaccord/depot/deploy/ansible
ansible-playbook -i inventories/staging/hosts.yml playbooks/services-server.yml --connection local --tags base
```

## Post-Installation

After running this role:

1. Verify Docker is running: `systemctl status docker`
2. Check naaccord user: `id naaccord`
3. Test Docker access: `sudo -u naaccord docker ps`
4. Verify zsh installation: `zsh --version`
5. Check directory permissions: `ls -la /opt/naaccord`

## Notes

- SELinux is set to permissive mode for PHI compliance testing
- Docker log rotation is configured to prevent disk space issues
- All users with login shells get oh-my-zsh with agnoster theme
- The naaccord user has passwordless sudo access
