from django.http import HttpResponseForbidden, HttpResponse
from functools import wraps


def can(user_permission_attribute):
    """
    This decorator checks if the user has the permission to access the view. It does this by passing the
    user_permission_attribute to the decorator. The user_permission_attribute is the name of an attribute on the
    user model that determines if the user has the permission to access the view.

    This enforces the convention that the user model has attributes that start with "can_" to determine if the user
    has the permission to access the view. For this reason, you should pass the name of the attribute without the
    "can_" prefix. For example, if the attribute on the user model is "can_view_dashboard", you should pass
     "view_dashboard"
    """

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(self, request, *args, **kwargs):
            property_name = (
                user_permission_attribute
                if user_permission_attribute.startswith("can_")
                else f"can_{user_permission_attribute}"
            )

            has_permission = getattr(request.user, property_name, None)
            if not has_permission:
                return HttpResponse("Permission Denied")
            return view_func(self, request, *args, **kwargs)

        return _wrapped_view

    return decorator


def member_of(user, group_name):
    return user.groups.filter(name=group_name).exists()
