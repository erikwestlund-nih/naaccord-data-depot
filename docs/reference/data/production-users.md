# Production Users Summary

**Last Updated:** October 10, 2025

## Overview

Production seed data configured for 18 users across 3 cohorts.

## User Breakdown

### NA Accord Administrators (5 users)
Full system access - can see and manage ALL cohorts

| Name | Email | Username | Staff | Superuser |
|------|-------|----------|-------|-----------|
| Erik Westlund | ewestlund@jhu.edu | ewestlund | ✅ | ✅ |
| Andre Hackman | ahackman@jhu.edu | ahackman | ✅ | ✅ |
| Keri Althoff | kalothoff@jhu.edu | kalthoff | ✅ | ❌ |
| Brenna Hogan | bhogan7@jhu.edu | bhogan | ✅ | ❌ |
| Catherine Lesko | clesko2@jhu.edu | clesko | ✅ | ❌ |

### Cohort Managers (13 users)
Can manage submissions for assigned cohorts only

#### JHHCC (Cohort ID: 6) - 4 users
| Name | Email | Username |
|------|-------|----------|
| LaQuita Snow | lsnow7@jhu.edu | lsnow |
| Jeanne Keruly | jkeruly@jhmi.edu | jkeruly |
| Richard Moore | rdmoore@jhmi.edu | rmoore |
| Todd Fojo | Anthony.Fojo@jhmi.edu | tfojo |

#### MACS/WIHS Combined Cohort Study (MWCCS) (Cohort ID: 22) - 5 users
| Name | Email | Username |
|------|-------|----------|
| Srijana Lawa | slawa1@jhu.edu | slawa |
| Mateo Bandala Jacques | abandal1@jhmi.edu | abandala |
| Stephen Gange | sgange@jhu.edu | sgange |
| Elizabeth Topper | etopper@jhu.edu | etopper |
| Amber D'Souza | gdsouza2@jhu.edu | adsouza |

#### Einstein/Montefiore (Cohort ID: 33) - 4 users
**Note:** Cohort name pending confirmation

| Name | Email | Username |
|------|-------|----------|
| David Hanna | david.hanna@einsteinmed.edu | dhanna |
| Uriel Felsen | UFELSEN@montefiore.org | ufelsen |
| Mindy Ginsberg | mindy.ginsberg@einsteinmed.edu | mginsberg |
| Noel Relucio | noel.relucio@einsteinmed.edu | nrelucio |

## Files Ready for Deployment

✅ **cohorts.csv** - 33 cohorts (added Einstein/Montefiore as ID 33)
✅ **users_production.csv** - 18 users configured
✅ **user_groups_production.csv** - All users assigned to appropriate groups
✅ **cohort_memberships_production.csv** - Cohort managers assigned to their cohorts

## Deployment Command

When ready to deploy to production:

```bash
# On production services server (mrpznaaccorddb01.hosts.jhmi.edu)
cd /opt/naaccord/depot

# Load production users
docker exec -it naaccord-services python manage.py load_users_from_csv \
  --csv-dir resources/data/seed
```

## Permission Groups Structure

After cleanup, only 3 groups exist:

1. **NA Accord Administrators** - Full system access (5 users)
2. **Cohort Managers** - Manage assigned cohorts (13 users)
3. **Cohort Viewers** - Read-only access (0 users currently)

Legacy groups (Administrators, Data Managers, Researchers, Coordinators, Viewers) have been removed from seeding.

## Cleanup Commands

To remove legacy groups from existing databases:

```bash
# Check what would be removed
python manage.py remove_legacy_groups --dry-run

# Migrate users and remove legacy groups
python manage.py remove_legacy_groups --migrate-users
```

## Next Steps

1. ✅ Confirm Einstein/Montefiore cohort name
2. Add additional cohort users as needed
3. Test seeding in staging environment
4. Deploy to production

## Notes

- All Cohort Manager users have `is_staff=False, is_superuser=False`
- NA Accord Administrators don't need explicit cohort memberships (can see all)
- Cohort Managers only see their assigned cohort(s)
- SAML authentication required for all logins (no password auth)
