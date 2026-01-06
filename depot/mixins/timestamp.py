from django.utils import timezone
from django.utils.timesince import timesince


class TimestampMixin:
    """Mixin to provide human-friendly timestamp formatting"""
    
    def time_ago(self, timestamp_field='created_at'):
        """
        Return a human-friendly time difference for the given timestamp field.
        
        Args:
            timestamp_field (str): Name of the timestamp field to format
            
        Returns:
            str: Human-readable time difference (e.g., "2 hours ago", "just now")
        """
        timestamp = getattr(self, timestamp_field, None)
        if not timestamp:
            return ""
        
        # Calculate time difference in seconds
        now = timezone.now()
        diff_seconds = (now - timestamp).total_seconds()
        
        # If less than 60 seconds, return "just now"
        if diff_seconds < 60:
            return "just now"
        
        # Otherwise use Django's timesince
        time_diff = timesince(timestamp, now)
        # timesince returns something like "2 hours, 3 minutes"
        # Let's take just the first part for brevity
        first_part = time_diff.split(',')[0].strip()
        
        # Special case for "0 minutes"
        if first_part == "0 minutes":
            return "just now"
        
        return first_part + ' ago'
    
    def uploaded_ago(self):
        """Return a human-friendly time difference since upload."""
        return self.time_ago('uploaded_at')
    
    def created_ago(self):
        """Return a human-friendly time difference since creation."""
        return self.time_ago('created_at')
    
    def updated_ago(self):
        """Return a human-friendly time difference since last update."""
        return self.time_ago('updated_at')