from django.conf import settings
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class NotebookTemplateMapper:
    """Maps data file types to their Quarto notebook templates."""
    
    def __init__(self):
        self.templates_dir = Path(settings.BASE_DIR) / 'depot' / 'notebooks' / 'audit'
        self._default_template = 'generic_audit.qmd'
        logger.debug(f"Initializing NotebookTemplateMapper with templates_dir: {self.templates_dir}")

    def get_template(self, data_file_type_name: str) -> str:
        """
        Get the Quarto template for a data file type.
        Currently always returns the generic template.
        
        Args:
            data_file_type_name: The name of the data file type
            
        Returns:
            str: The template name to use
        """
        logger.debug(f"Getting template for data_file_type: {data_file_type_name}")
        logger.debug(f"Using default template: {self._default_template}")
        return self._default_template

# Create a singleton instance
notebook_templates = NotebookTemplateMapper() 