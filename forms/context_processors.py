from .models import User, Response


def sidebar_flags(request):
    uid = request.session.get("user_id")
    user = User.objects.filter(pk=uid).first() if uid else None
    if user is None:
        return {}
    is_hod = user.headed_departments.exists()
    pending = 0
    if is_hod:
        pending = (Response.objects.filter(department__hod=user, status="pending_hod")
                   .exclude(respondent=user).count())
    return {"is_hod": is_hod, "pending_approvals": pending}