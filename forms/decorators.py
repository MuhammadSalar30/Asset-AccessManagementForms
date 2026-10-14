# forms/decorators.py
from functools import wraps
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from .models import User


def current_user(request):
    uid = request.session.get("user_id")
    return User.objects.filter(pk=uid).first() if uid else None


def admin_required(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        user = current_user(request)
        if user is None:
            return redirect("login")
        if not user.is_admin:
            raise PermissionDenied   # 403 for normal users
        request.org_user = user
        return view(request, *args, **kwargs)
    return wrapper


def hod_required(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        user = current_user(request)
        if user is None:
            return redirect("login")
        if not user.headed_departments.exists():
            raise PermissionDenied   # only department HODs
        request.org_user = user
        return view(request, *args, **kwargs)
    return wrapper
def responses_access_required(view):
    """Admins and department HODs only."""
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        user = current_user(request)
        if user is None:
            return redirect("login")
        if not (user.is_admin or user.headed_departments.exists()):
            raise PermissionDenied
        request.org_user = user
        return view(request, *args, **kwargs)
    return wrapper