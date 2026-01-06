from django import template
from depot.models import Notebook

register = template.Library()

@register.simple_tag
def get_notebook(notebook_id):
    """Fetch a notebook by ID"""
    if not notebook_id:
        return None
    try:
        return Notebook.objects.get(id=notebook_id)
    except Notebook.DoesNotExist:
        return None