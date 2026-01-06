# Hosts Management Role

## Overview

Manages `/etc/hosts` entries for NA-ACCORD's WireGuard tunnel network. Adds internal DNS names for the encrypted PHI tunnel between web and services servers.

## Purpose

The NA-ACCORD architecture uses a WireGuard tunnel for all PHI data transmission between servers. This role adds static hostname entries so services can reference each other by name instead of IP addresses.

## What It Does

Adds WireGuard tunnel IP addresses to `/etc/hosts`:
- `10.100.0.11 services.naaccord.internal` - Services server tunnel endpoint
- `10.100.0.10 web.naaccord.internal` - Web server tunnel endpoint

## Requirements

- Root/sudo access
- `/etc/hosts` file exists (standard on all Linux systems)

## Variables

None - uses hardcoded WireGuard tunnel IPs from architecture design.

## Dependencies

None

## Usage

Applied automatically by:
- `playbooks/services-server.yml`
- `playbooks/web-server.yml`

Can also be run standalone:
```bash
ansible-playbook -i inventories/staging/hosts.yml \
  --tags hosts \
  playbooks/services-server.yml
```

## Implementation Notes

- Uses `lineinfile` module for safe updates (preserves existing entries)
- Idempotent - can run multiple times safely
- Creates backup of `/etc/hosts` before changes
- No handlers needed - changes are immediately effective

## Security

- No sensitive data
- Standard system file modification
- Backup created automatically
