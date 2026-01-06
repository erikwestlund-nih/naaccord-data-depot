"""
Group name constants for NA-ACCORD.
Centralizes group definitions to avoid hardcoded strings throughout the codebase.
"""


class Groups:
    """New simplified group structure."""
    NA_ACCORD_ADMINISTRATORS = "NA Accord Administrators"
    COHORT_MANAGERS = "Cohort Managers"
    COHORT_VIEWERS = "Cohort Viewers"
    
    # Legacy groups (temporary - for migration compatibility)
    LEGACY_ADMINISTRATORS = "Administrators"
    LEGACY_DATA_MANAGERS = "Data Managers"
    LEGACY_RESEARCHERS = "Researchers"
    LEGACY_COORDINATORS = "Coordinators"
    LEGACY_VIEWERS = "Viewers"
    
    @classmethod
    def get_new_groups(cls):
        """Get list of new group names."""
        return [
            cls.NA_ACCORD_ADMINISTRATORS,
            cls.COHORT_MANAGERS,
            cls.COHORT_VIEWERS,
        ]
    
    @classmethod
    def get_legacy_groups(cls):
        """Get list of legacy group names."""
        return [
            cls.LEGACY_ADMINISTRATORS,
            cls.LEGACY_DATA_MANAGERS,
            cls.LEGACY_RESEARCHERS,
            cls.LEGACY_COORDINATORS,
            cls.LEGACY_VIEWERS,
        ]
    
    @classmethod
    def get_migration_mapping(cls):
        """Get mapping from legacy groups to new groups."""
        return {
            cls.LEGACY_ADMINISTRATORS: cls.NA_ACCORD_ADMINISTRATORS,
            cls.LEGACY_DATA_MANAGERS: cls.NA_ACCORD_ADMINISTRATORS,
            cls.LEGACY_RESEARCHERS: cls.COHORT_MANAGERS,
            cls.LEGACY_COORDINATORS: cls.COHORT_MANAGERS,
            cls.LEGACY_VIEWERS: cls.COHORT_VIEWERS,
        }