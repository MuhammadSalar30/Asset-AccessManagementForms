from django.shortcuts import render,redirect
from django.urls import path
from .decorators import responses_access_required
from django.http import HttpResponse
from rest_framework.decorators import api_view
from rest_framework.response import Response 
#from django.contrib.auth.models import User
from django.contrib.auth.hashers import make_password,check_password
from django.http import JsonResponse
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.conf import settings
from django.core.exceptions import PermissionDenied
from .models import ApprovalLog
from .builtin_forms import create_builtin_form, sync_folder_options
from .models import SharedFolder
from .decorators import hod_required
from .models import ApprovalLog, AccessGrant
import json
import os
from datetime import datetime, timedelta, time as dtime
from collections import Counter, defaultdict
from django.utils.dateparse import parse_date, parse_time
from .models import Response as FormResponse, Answer, AnswerFile
from .models import User, Department, Form, FormInvite, FormElement, ElementOption
from .decorators import admin_required
# forms/views.py
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
import threading
from django.core.mail import send_mail, send_mass_mail
from django.db.models import Count, Q

from django.core.mail import send_mail
from django.template.loader import render_to_string
from rest_framework.response import Response as DRFResponse
from django.contrib import messages
import time
import re
FOLDER_QUESTION = re.compile(r"^\s*folder\s*\d*\b", re.IGNORECASE)

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_SHORT_LEN = 500
MAX_LONG_LEN = 5000
BLOCKED_EXTENSIONS = {".exe", ".bat", ".cmd", ".com", ".msi", ".dll", ".scr",
                      ".js", ".vbs", ".ps1", ".sh", ".php", ".py"}


def is_form_owner(request, form):
    return "user_id" in request.session and str(form.owner_id) == request.session["user_id"]


def form_access_status(request, form):
    """Returns 'ok', 'not_found' or 'denied' for the current visitor."""
    owner = is_form_owner(request, form)

    if not form.is_published and not owner:
        return "not_found"

    if form.access_type == "restricted" and not owner:
        email = request.session.get("user_email", "").strip().lower()
        if not email or not form.invites.filter(email=email).exists():
            return "denied"
    if form.access_type == "departments" and not owner:
        uid = request.session.get("user_id")
        if not uid or not form.departments.filter(members__pk=uid).exists():
            return "denied"
    return "ok"
# Create your views here.
def Homepage(Request):
    return HttpResponse("Home Page")
def Forms(Request):
    return HttpResponse("Form")
@api_view(['GET'])
def test_api(request):
    return Response({
        "message": "Django is connected to React!"
    })


def homepage_view(request):
    return render(request,"homepage.html")
def register_view(request):
    ctx = {"departments": Department.objects.order_by("name")}

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        email = request.POST.get("email", "").strip().lower()
        department_id = request.POST.get("department", "")
        password = request.POST.get("password")
        confirm_password = request.POST.get("confirm_password")

        if not all([name, email, department_id, password, confirm_password]):
            messages.error(request, "All fields are required.")
            return render(request, "signup.html", ctx)

        if password != confirm_password:
            messages.error(request, "Passwords do not match.")
            return render(request, "signup.html", ctx)

        department = Department.objects.filter(pk=department_id).first() if department_id.isdigit() else None
        if department is None:
            messages.error(request, "Please choose a valid department.")
            return render(request, "signup.html", ctx)

        if User.objects.filter(email__iexact=email).exists():
            messages.error(request, "An account with this email already exists.")
            return render(request, "signup.html", ctx)

        User.objects.create(name=name, email=email, department=department,
                            password=make_password(password))
        messages.success(request, "Account created successfully.")
        return redirect("login")

    return render(request, "signup.html", ctx)
@admin_required
def settings_view(request):
    if "user_id" not in request.session:
        return redirect("login")
    return render(request, "manage/settings.html")
def is_admin_session(request):
    return request.session.get("user_role") == "admin"

def login_view(request):
    if request.method == "POST":
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password", "")
        remember = request.POST.get("remember")

        if not email or not password:
            messages.error(request, "Email and password are required.")
            return render(request, "login.html")

        user = User.objects.filter(email__iexact=email).first()
        if user is None or not check_password(password, user.password):
            messages.error(request, "Invalid email or password.")
            return render(request, "login.html")
        list(messages.get_messages(request))   # discard any leftover error messages
        request.session["user_id"] = str(user.user_id)
        request.session["user_name"] = user.name
        request.session["user_email"] = user.email
        request.session["department"] = user.department.name if user.department else ""
        request.session["user_role"] = "admin" if user.is_admin else "user"

        request.session.set_expiry(1209600 if remember else 0)
        #return redirect("forms_list")
        next_url = request.session.pop("after_login", None)
        if next_url and next_url.startswith("/"):
            return redirect(next_url)
        #return redirect("manage_org" if user.is_admin else "forms_list")
        if user.is_admin:
            return redirect("manage_org")
        if user.headed_departments.exists():
            return redirect("hod_approvals")
        return redirect("my_assets")

    return render(request, "login.html")
def logout_view(request):
    request.session.flush()
    return redirect("login")
def notify_invite_access(form, invite):

    permission_text = {
        "respond": "respond to",
        "edit": "edit",
        "both": "edit and respond to",
    }.get(invite.permission, "respond to")

    #link = f"http://10.1.5.47:8000/f/{form.form_id}/"
    #edit_link = f"http://10.1.5.47:8000/forms/edit/{form.form_id}/"

    link = f"{settings.SITE_URL}/f/{form.form_id}/"
    edit_link = f"{settings.SITE_URL}/forms/edit/{form.form_id}/"

    subject = f"You've been given access to \"{form.title}\""

    body_lines = [
        f'You now have access to {permission_text} the form "{form.title}".',
        "",
    ]

    if invite.can_respond:
        body_lines.append(f"Respond to the form: {link}")
    if invite.can_edit:
        body_lines.append(f"Edit the form: {edit_link}")

    body = "\n".join(body_lines)

    try:
        send_mail(subject, body, None, [invite.email], fail_silently=False)
    except Exception as e:
        print(f"Invite notification failed: {e}")
def forms_list_view(request):

    if "user_id" not in request.session:
        return redirect("login")

    forms = Form.objects.filter(
        owner__user_id=request.session["user_id"]
    ).order_by("-updated_at")

    context = {
        "user_name": request.session.get("user_name"),
        "forms": forms,
    }

    return render(request, "forms_list.html", context)
def _can_edit_form(request, form):
    if is_form_owner(request, form) or _session_is_admin(request):
        return True
    email = request.session.get("user_email", "").strip().lower()
    return bool(email) and form.invites.filter(email=email, permission__in=("edit", "both")).exists()


def _get_manageable_form(request, form_id):
    form = Form.objects.filter(form_id=form_id).first()
    if form and (is_form_owner(request, form) or _session_is_admin(request)):
        return form
    return None
def forms_view(request, form_id=None):

    if "user_id" not in request.session:
        return redirect("login")
    form = None
    elements_json = "[]"
    if form_id:
        form = Form.objects.prefetch_related("elements__options").filter(form_id=form_id).first()
        if form is None:
            return HttpResponse("Form not found.", status=404)
        if not _can_edit_form(request, form):
            return HttpResponse("You don't have permission to edit this form.", status=403)

        elements_data = []

        for el in form.elements.order_by("order"):

            elements_data.append({
                "type": el.element_type,
                "id": str(el.element_id),
                "question": el.question_text,
                "questionType": el.question_type,
                "options": [opt.option_text for opt in el.options.all()],
                "required": el.is_required,
                "title": el.title,
                "description": el.description,
                "scaleMin": el.scale_min,
                "scaleMax": el.scale_max,
                "scaleMinLabel": el.scale_min_label,
                "scaleMaxLabel": el.scale_max_label,
                "gridRows": el.grid_rows.splitlines() if el.grid_rows else [],
                "maxFiles": el.max_files,
                "imageUrl": el.image.url if el.image else None,
            })
        elements_json = json.dumps(elements_data)

    return render(request, "forms.html", {
        "user_name": request.session.get("user_name"),
        "form": form,
        "elements_json": elements_json,
    })
@transaction.atomic
def save_form(request):

    if request.method != "POST":
        return JsonResponse({"success": False, "message": "Invalid request method."}, status=405)

    if "user_id" not in request.session:
        return JsonResponse({"success": False, "message": "You must be logged in."}, status=401)

    try:
        user = User.objects.get(user_id=request.session["user_id"])

        title = request.POST.get("title", "Untitled Form")
        description = request.POST.get("description", "")
        existing_form_id = request.POST.get("form_id", "").strip()

        if existing_form_id:
            #try:
                #form = Form.objects.get(form_id=existing_form_id, owner__user_id=request.session["user_id"])
            #except Form.DoesNotExist:
                #return JsonResponse({"success": False, "message": "Form not found."}, status=404)
            #form.title = title
            
            form = Form.objects.filter(form_id=existing_form_id).first()
            if form is None:
                return JsonResponse({"success": False, "message": "Form not found."}, status=404)
            if not _can_edit_form(request, form):
                return JsonResponse({"success": False, "message": "You don't have permission to edit this form."}, status=403)
            form.title = title
            form.description = description
            form.save()
        else:
            form = Form.objects.create(owner=user, owner_name=user.name, title=title, description=description)

        element_count = int(request.POST.get("element_count", 0))
        kept_element_ids = []

        for index in range(element_count):

            element_type = request.POST.get(f"element_type_{index}")
            if not element_type:
                continue

            is_required = request.POST.get(f"is_required_{index}") == "true"
            db_id = request.POST.get(f"element_db_id_{index}", "").strip()
            uploaded_image = request.FILES.get(f"image_{index}")

            existing_element = None
            if db_id:
                existing_element = FormElement.objects.filter(form=form, element_id=db_id).first()

            field_values = dict(
                order=index,
                element_type=element_type,
                is_required=is_required,
                question_text=request.POST.get(f"question_text_{index}", ""),
                question_type=request.POST.get(f"question_type_{index}", ""),
                title=request.POST.get(f"title_{index}", ""),
                description=request.POST.get(f"description_{index}", ""),
                max_files=int(request.POST.get(f"max_files_{index}", 1) or 1),
                scale_min=request.POST.get(f"scale_min_{index}") or None,
                scale_max=request.POST.get(f"scale_max_{index}") or None,
                scale_min_label=request.POST.get(f"scale_min_label_{index}", ""),
                scale_max_label=request.POST.get(f"scale_max_label_{index}", ""),
                grid_rows=request.POST.get(f"grid_rows_{index}", ""),
            )

            if existing_element:
                for key, value in field_values.items():
                    setattr(existing_element, key, value)

                if uploaded_image:
                    existing_element.image = uploaded_image
                # agar nayi image upload nahi hui, purani image chhuti hui nahi, wahi rehti hai

                existing_element.save()
                element = existing_element
                element.options.all().delete()
            else:
                element = FormElement.objects.create(image=uploaded_image, form=form, **field_values)

            kept_element_ids.append(element.element_id)

            options = request.POST.getlist(f"options_{index}")
            for opt_index, option_text in enumerate(options):
                if option_text.strip():
                    ElementOption.objects.create(element=element, option_text=option_text, order=opt_index)

        # jo elements pehle thе lekin ab sections array mein nahi hain, wo user ne delete kiye thе
        if existing_form_id:
            form.elements.exclude(element_id__in=kept_element_ids).delete()

        return JsonResponse({"success": True, "message": "Form saved successfully.", "form_id": str(form.form_id)})

    except User.DoesNotExist:
        return JsonResponse({"success": False, "message": "User not found."}, status=404)

    except Exception as e:
        return JsonResponse({"success": False, "message": str(e)}, status=500)


@transaction.atomic
def publish_form(request, form_id):

    if request.method != "POST":
        return JsonResponse({"success": False, "message": "Invalid request method."}, status=405)

    if "user_id" not in request.session:
        return JsonResponse({"success": False, "message": "You must be logged in."}, status=401)

    #try:
     #   form = Form.objects.get(form_id=form_id, owner__user_id=request.session["user_id"])
    #except Form.DoesNotExist:
     #   return JsonResponse({"success": False, "message": "Form not found."}, status=404)
    form = _get_manageable_form(request, form_id)
    if form is None:
        return JsonResponse({"success": False, "message": "Form not found."}, status=404)
    action = request.POST.get("action", "publish")

    if action == "unpublish":
        form.is_published = False
        form.published_at = None
        form.save()
        return JsonResponse({"success": True, "is_published": False, "message": "Form unpublished."})
    if form.access_type == "departments" and not form.departments.exists():
        return JsonResponse({"success": False,
                             "message": "Select at least one department before publishing."}, status=400)
    form.is_published = True
    form.published_at = timezone.now()
    form.save()
    if form.access_type == "departments":
        notify_departments(form, set(form.departments.values_list("pk", flat=True)))

    publish_link = request.build_absolute_uri(f"/f/{form.form_id}/")

    return JsonResponse({
        "success": True,
        "is_published": True,
        "publish_link": publish_link,
        "access_type": form.access_type,
        "message": "Form published."
    })
def _session_is_admin(request):
    uid = request.session.get("user_id")
    return bool(uid) and User.objects.filter(pk=uid, role="admin").exists()


def notify_departments(form, department_ids):
    """Email every employee of the given departments (one individual email each)."""
    users = (User.objects.filter(department_id__in=department_ids)
             .exclude(pk=form.owner_id))
    link = f"{settings.SITE_URL}/f/{form.form_id}/"
    seen, messages_to_send = set(), []
    for u in users:
        addr = (u.email or "").strip().lower()
        if not addr or addr in seen:
            continue
        seen.add(addr)
        body = (f"Hello {u.name},\n\n"
                f'A new form is available for your department: "{form.title}".\n\n'
                f"Open it here (you need to be logged in):\n{link}\n")
        messages_to_send.append((f"New form: {form.title}", body, None, [addr]))
    if not messages_to_send:
        return 0

    def _send():
        try:
            send_mass_mail(tuple(messages_to_send), fail_silently=False)
        except Exception as e:
            print(f"Department notification failed: {e}")

    transaction.on_commit(lambda: threading.Thread(target=_send, daemon=True).start())
    return len(messages_to_send)

@transaction.atomic
def manage_access(request, form_id):

    if "user_id" not in request.session:
        return JsonResponse({"success": False, "message": "You must be logged in."}, status=401)
    form = _get_manageable_form(request, form_id)
    if form is None:
        return JsonResponse({"success": False, "message": "Form not found."}, status=404)
    #try:
       # form = Form.objects.get(form_id=form_id, owner__user_id=request.session["user_id"])
    #except Form.DoesNotExist:
       # return JsonResponse({"success": False, "message": "Form not found."}, status=404)

    # -------- GET: return current state to populate the modal --------

    if request.method == "GET":
        invites = list(form.invites.values("invite_id", "email", "permission").order_by("email"))
        for i in invites:
            i["invite_id"] = str(i["invite_id"])
        selected_ids = set(form.departments.values_list("pk", flat=True))
        return JsonResponse({
            "success": True,
            "access_type": form.access_type,
            "invites": invites,
            "departments": [
                {"id": d.pk, "name": d.name, "selected": d.pk in selected_ids}
                for d in Department.objects.order_by("name")
            ],
        })
    # -------- POST: mutate access settings --------
    if request.method != "POST":
        return JsonResponse({"success": False, "message": "Invalid request method."}, status=405)

    action = request.POST.get("action")

    if action == "set_access_type":
        access_type = request.POST.get("access_type")

        #if access_type not in ("anyone", "restricted"):
            #return JsonResponse({"success": False, "message": "Invalid access type."}, status=400)
        if access_type not in ("anyone", "restricted", "departments"):
            return JsonResponse({"success": False, "message": "Invalid access type."}, status=400)
        if access_type == "departments" and not _session_is_admin(request):
            return JsonResponse({"success": False, "message": "Only admins can share with departments."}, status=403)
        form.access_type = access_type
        form.save()

        return JsonResponse({"success": True, "access_type": form.access_type})

    if action == "add_invite":
        email = (request.POST.get("email") or "").strip().lower()
        permission = request.POST.get("permission", "respond")

        if not email:
            return JsonResponse({"success": False, "message": "Email is required."}, status=400)
        if permission not in ("respond", "edit", "both"):
            permission = "respond"

        invite, created = FormInvite.objects.get_or_create(form=form, email=email, defaults={"permission": permission})
        if not created:
            invite.permission = permission
            invite.save()
        notify_invite_access(form, invite)

        return JsonResponse({
            "success": True,
            "invite": {"invite_id": str(invite.invite_id), "email": invite.email,"permission":invite.permission}
        })
    if action == "update_permission":
        invite_id = request.POST.get("invite_id")
        permission = request.POST.get("permission")

        if permission not in ("respond", "edit", "both"):
            return JsonResponse({"success": False, "message": "Invalid permission."}, status=400)
        try:
            invite = FormInvite.objects.get(form=form, invite_id=invite_id)
        except FormInvite.DoesNotExist:
            return JsonResponse({"success": False, "message": "Invite not found."}, status=404)

        invite.permission = permission
        invite.save()

        notify_invite_access(form, invite)

        return JsonResponse({"success": True})

    if action == "remove_invite":
        invite_id = request.POST.get("invite_id")

        FormInvite.objects.filter(form=form, invite_id=invite_id).delete()

        return JsonResponse({"success": True})
    if action == "set_departments":
        if not _session_is_admin(request):
            return JsonResponse({"success": False, "message": "Only admins can share with departments."}, status=403)
        ids = [int(i) for i in request.POST.getlist("departments") if i.isdigit()]
        new_set = set(Department.objects.filter(pk__in=ids).values_list("pk", flat=True))
        old_set = set(form.departments.values_list("pk", flat=True))
        form.departments.set(new_set)

        emailed = 0
        added = new_set - old_set
        if form.is_published and form.access_type == "departments" and added:
            emailed = notify_departments(form, added)   # only newly added departments
        return JsonResponse({"success": True, "selected": sorted(new_set), "emailed": emailed})
    

   


def view_form(request, form_id):
    if "user_id" not in request.session:
        request.session["after_login"] = request.get_full_path()
        return redirect("login")

    try:
        form = Form.objects.prefetch_related("elements__options").get(form_id=form_id)
    except Form.DoesNotExist:
        return render(request, "form_not_found.html", status=404)

    status = form_access_status(request, form)

    if status == "not_found":
        return render(request, "form_not_found.html", status=404)
    if status == "denied":
        return render(request, "form_access_denied.html", status=403)

    return render(request, "public_form.html", {"form": form, "elements": form.elements.all()})


def validate_answer(element, post, files):
    """
    Returns (stored_text, uploaded_files, error_message).
    stored_text is "" when the question was left blank.
    """
    key = f"answer_{element.element_id}"
    qtype = element.question_type
    required = element.is_required
    required_msg = "This question is required."
    valid_options = [o.option_text for o in element.options.all()]

    def blank():
        return "", [], (required_msg if required else None)

    # ---- short answer / paragraph ----
    if qtype in ("short", "paragraph"):
        value = post.get(key, "").strip()
        limit = MAX_SHORT_LEN if qtype == "short" else MAX_LONG_LEN
        if not value:
            return blank()
        if len(value) > limit:
            return "", [], f"Please keep this answer under {limit} characters."
        return value, [], None

    # ---- multiple choice / dropdown ----
    if qtype in ("mcq", "dropdown"):
        value = post.get(key, "")
        if not value:
            return blank()
        if value not in valid_options:
            return "", [], "Please choose one of the listed options."
        return value, [], None

    # ---- checkboxes ----
    if qtype == "checkbox":
        values = post.getlist(key)
        if not values:
            return blank()
        if any(v not in valid_options for v in values):
            return "", [], "Please choose only from the listed options."
        return json.dumps(values), [], None

    # ---- linear scale ----
    if qtype == "linear_scale":
        raw = post.get(key, "").strip()
        if not raw:
            return blank()
        try:
            number = int(raw)
        except ValueError:
            return "", [], "Please pick a value on the scale."
        if number not in element.scale_range:
            return "", [], "That value is outside the scale."
        return str(number), [], None

    # ---- grids ----
    if qtype in ("mcq_grid", "checkbox_grid"):
        multi = qtype == "checkbox_grid"
        result = {}
        for i, row in enumerate(element.grid_row_list):
            picked = post.getlist(f"{key}__{i}")
            if not multi:
                picked = picked[:1]
            if any(p not in valid_options for p in picked):
                return "", [], "Please choose only from the listed columns."
            if picked:
                result[row] = picked if multi else picked[0]
            elif required:
                return "", [], f"Please answer every row (missing: {row})."
        return (json.dumps(result) if result else ""), [], None

    # ---- date / time ----
    if qtype in ("date", "time"):
        raw = post.get(key, "").strip()
        if not raw:
            return blank()
        try:
            parsed = parse_date(raw) if qtype == "date" else parse_time(raw)
        except ValueError:
            parsed = None
        if parsed is None:
            return "", [], f"Please enter a valid {qtype}."
        return (parsed.isoformat() if qtype == "date" else parsed.strftime("%H:%M")), [], None

    # ---- file upload ----
    if qtype == "file_upload":
        uploads = files.getlist(key)
        if not uploads:
            return blank()
        if len(uploads) > element.max_files:
            return "", [], f"You can upload at most {element.max_files} file(s)."
        for f in uploads:
            if f.size > MAX_UPLOAD_BYTES:
                return "", [], f"“{f.name}” is larger than 10 MB."
            if os.path.splitext(f.name)[1].lower() in BLOCKED_EXTENSIONS:
                return "", [], f"“{f.name}” is not an allowed file type."
        return "", uploads, None

    return "", [], None
@transaction.atomic
def submit_response(request, form_id):

    if request.method != "POST":
        return JsonResponse({"success": False, "message": "Invalid request method."}, status=405)

    try:
        form = Form.objects.prefetch_related("elements__options").get(form_id=form_id)
    except Form.DoesNotExist:
        return JsonResponse({"success": False, "message": "This form doesn't exist."}, status=404)

    if not form.is_published:
        return JsonResponse({"success": False, "message": "This form isn't accepting responses."}, status=403)

    if form_access_status(request, form) != "ok":
        return JsonResponse({"success": False, "message": "You don't have access to this form."}, status=403)
    if "user_id" not in request.session:
        return JsonResponse({"success": False, "message": "Please log in to submit a request."}, status=401)

    respondent = (User.objects.select_related("department__hod")
                  .filter(pk=request.session["user_id"]).first())
    department = respondent.department if respondent else None
    if respondent is None or department is None or department.hod_id is None:
        return JsonResponse({
            "success": False,
            "message": "Your department has no HOD assigned yet, so this request can't be routed. "
                       "Please contact an administrator.",
        }, status=400)
    # ---- validate everything first; save nothing if anything fails ----
    errors = {}
    collected = []

    for element in form.elements.all():

        if element.element_type != "question":
            continue

        stored, uploads, error = validate_answer(element, request.POST, request.FILES)

        if error:
            errors[str(element.element_id)] = error
        elif stored or uploads:
            collected.append((element, stored, uploads))

    if errors:
        return JsonResponse({
            "success": False,
            "message": "Please fix the highlighted questions.",
            "errors": errors,
        }, status=400)

    if not collected:
        return JsonResponse({
            "success": False,
            "message": "Please answer at least one question before submitting.",
        }, status=400)
    new_code = None
    if form.purpose == "asset_access" and form.code_element_id:
        for element, stored, uploads in collected:
            if element.pk == form.code_element_id:
                new_code = (stored or "").strip() or None
        if new_code:
            if respondent.employee_code and respondent.employee_code.lower() != new_code.lower():
                return JsonResponse({"success": False,
                    "message": "The employee code does not match the code on your account."}, status=400)
            if User.objects.filter(employee_code__iexact=new_code).exclude(pk=respondent.pk).exists():
                return JsonResponse({"success": False,
                    "message": "This employee code belongs to another account. Please contact an administrator."}, status=400)
    # ---- save ----

        # ---- save ----
    
    is_own_hod = department.hod_id == respondent.pk   # a HOD can't approve their own request

    response = FormResponse.objects.create(
        form=form, respondent=respondent, department=department,
        status="pending_it" if is_own_hod else "pending_hod",
    )
    if new_code and not respondent.employee_code:
        respondent.employee_code = new_code
        respondent.save(update_fields=["employee_code"])

    for element, stored, uploads in collected:
        answer = Answer.objects.create(response=response, element=element, answer_text=stored)
        for upload in uploads:
            AnswerFile.objects.create(answer=answer, file=upload)

    if is_own_hod:
        ApprovalLog.objects.create(
            response=response, stage="hod", approver=respondent, decision="approved",
            comment="Auto-approved: the requester is the department HOD.",
        )
    else:
        transaction.on_commit(lambda: notify_hod_new_request(response))

    return JsonResponse({"success": True, "message": "Your request has been submitted for approval."})

def build_summary(element, answers):

    qtype = element.question_type
    summary = {"element": element, "answered": len(answers), "answers": answers}

    if qtype in ("mcq", "dropdown", "checkbox"):

        counts = Counter()
        for a in answers:
            value = a.value
            counts.update(value if isinstance(value, list) else [value])

        summary["kind"] = "choice"
        summary["rows"] = [
            {
                "label": opt.option_text,
                "count": counts.get(opt.option_text, 0),
                "percent": round(100 * counts.get(opt.option_text, 0) / len(answers)) if answers else 0,
            }
            for opt in element.options.all()
        ]

    elif qtype == "linear_scale":

        counts = Counter()
        for a in answers:
            if a.answer_text.lstrip("-").isdigit():
                counts[int(a.answer_text)] += 1

        total = sum(counts.values())
        summary["kind"] = "choice"
        summary["rows"] = [
            {
                "label": n,
                "count": counts.get(n, 0),
                "percent": round(100 * counts.get(n, 0) / total) if total else 0,
            }
            for n in element.scale_range
        ]
        summary["average"] = round(sum(n * c for n, c in counts.items()) / total, 2) if total else None

    elif qtype in ("mcq_grid", "checkbox_grid"):

        columns = [o.option_text for o in element.options.all()]
        rows = element.grid_row_list
        counts = {row: Counter() for row in rows}

        for a in answers:
            for row, picked in a.grid_pairs:
                if row in counts:
                    counts[row].update(picked if isinstance(picked, list) else [picked])

        summary["kind"] = "grid"
        summary["columns"] = columns
        summary["table"] = [
            {"row": row, "cells": [counts[row].get(c, 0) for c in columns]}
            for row in rows
        ]

    elif qtype == "file_upload":
        summary["kind"] = "file"

    else:
        summary["kind"] = "text"

    return summary


def view_responses(request, form_id):

    if "user_id" not in request.session:
        return redirect("login")

    try:
        form = Form.objects.get(form_id=form_id, owner__user_id=request.session["user_id"])
    except Form.DoesNotExist:
        return HttpResponse("Form not found.", status=404)

    elements = list(form.elements.filter(element_type="question").prefetch_related("options"))
    responses = list(form.responses.select_related("respondent").order_by("-submitted_at"))

    answers = (
        Answer.objects.filter(response__form=form)
        .select_related("element")
        .prefetch_related("files")
    )

    by_response = defaultdict(dict)
    by_element = defaultdict(list)

    for a in answers:
        by_response[a.response_id][a.element_id] = a
        by_element[a.element_id].append(a)

    for r in responses:
        r.rows = [
            {"element": el, "answer": by_response[r.response_id].get(el.element_id)}
            for el in elements
        ]

    summaries = [build_summary(el, by_element[el.element_id]) for el in elements]

    return render(request, "responses.html", {
        "form": form,
        "responses": responses,
        "summaries": summaries,
        "response_count": len(responses),
    })

from django.core.mail import send_mail
from django.template.loader import render_to_string


def notify_response_submitted(form, response):

    if form.access_type != "restricted":
        return

    recipients = list(form.invites.values_list("email", flat=True))
    if not recipients:
        return

    subject = f"New response: {form.title}"

    body = render_to_string("emails/new_response.txt", {
        "form": form,
        "response": response,
    })

    try:
        send_mail(subject, body, None, recipients, fail_silently=False)
    except Exception as e:
        # Don't let a broken mail server break the actual submission.
        print(f"Email notification failed: {e}")
@require_POST
def delete_form(request, form_id):
    if "user_id" not in request.session:
        return redirect("login")
    form = get_object_or_404(Form, form_id=form_id, owner_id=request.session["user_id"])
    title = form.title
    form.delete()
    messages.success(request, f'Form "{title}" was deleted.')
    return redirect("forms_list")
def _int_or_none(value):
    return int(value) if value and str(value).isdigit() else None


@admin_required
def manage_org(request):
    """Admin dashboard."""
    departments = (Department.objects.select_related("hod")
                   .annotate(member_count=Count("members", distinct=True),
                             form_count=Count("members__forms", distinct=True))
                   .order_by("name"))
    return render(request, "manage/dashboard.html", {
        "me": request.org_user,
        "total_users": User.objects.count(),
        "total_admins": User.objects.filter(role="admin").count(),
        "total_departments": departments.count(),
        "total_forms": Form.objects.count(),
        "published_forms": Form.objects.filter(is_published=True).count(),
        "total_responses": FormResponse.objects.count(),
        "no_hod": Department.objects.filter(hod__isnull=True).count(),
        "departments": departments,
        "recent_forms": Form.objects.select_related("owner").order_by("-created_at")[:6],
    })


@admin_required
def manage_departments(request):
    return render(request, "manage/departments.html", {
        "me": request.org_user,
        "departments": (Department.objects.select_related("hod")
                        .annotate(member_count=Count("members")).order_by("name")),
        "users": User.objects.order_by("name"),
    })


@admin_required
@require_POST
def create_department(request):
    name = request.POST.get("name", "").strip()
    if not name:
        messages.error(request, "Department name is required.")
    elif Department.objects.filter(name__iexact=name).exists():
        messages.error(request, "That department already exists.")
    else:
        Department.objects.create(name=name)
        messages.success(request, f'Department "{name}" created.')
    return redirect("manage_departments")


@admin_required
@require_POST
def set_hod(request, dept_id):
    dept = get_object_or_404(Department, pk=dept_id)
    uid = request.POST.get("hod")
    dept.hod = get_object_or_404(User, pk=uid) if uid else None
    dept.save(update_fields=["hod"])
    messages.success(request, f"HOD updated for {dept.name}.")
    return redirect("manage_departments")


@admin_required
@require_POST
def delete_department(request, dept_id):
    dept = get_object_or_404(Department, pk=dept_id)
    name = dept.name
    dept.delete()   # users in it become "no department"
    messages.success(request, f'Department "{name}" deleted.')
    return redirect("manage_departments")


@admin_required
def manage_users(request):
    q = request.GET.get("q", "").strip()
    dept = request.GET.get("department", "")
    users = User.objects.select_related("department").order_by("name")
    if q:
        users = users.filter(Q(name__icontains=q) | Q(email__icontains=q))
    if _int_or_none(dept):
        users = users.filter(department_id=int(dept))
    return render(request, "manage/users.html", {
        "me": request.org_user,
        "users": users,
        "departments": Department.objects.order_by("name"),
        "q": q,
        "f_dept": dept,
    })


@admin_required
@require_POST
def create_user(request):
    name = request.POST.get("name", "").strip()
    email = request.POST.get("email", "").strip().lower()
    password = request.POST.get("password", "")
    if not (name and email and password):
        messages.error(request, "Name, email and password are required.")
    elif User.objects.filter(email__iexact=email).exists():
        messages.error(request, "A user with that email already exists.")
    else:
        User.objects.create(name=name, email=email,
                            password=make_password(password),
                            department_id=_int_or_none(request.POST.get("department")))
        messages.success(request, f"User {name} created.")
    return redirect("manage_users")


@admin_required
@require_POST
def toggle_admin(request, user_id):
    target = get_object_or_404(User, pk=user_id)
    if target.pk == request.org_user.pk:
        messages.error(request, "You can't change your own admin status.")
    else:
        target.role = "admin" if request.POST.get("make_admin") == "1" else "user"
        target.save(update_fields=["role"])
        messages.success(request, f"Role updated for {target.name}.")
    return redirect("manage_users")


@admin_required
@require_POST
def set_user_department(request, user_id):
    target = get_object_or_404(User, pk=user_id)
    target.department = Department.objects.filter(pk=_int_or_none(request.POST.get("department"))).first()
    target.save(update_fields=["department"])
    messages.success(request, f"Department updated for {target.name}.")
    return redirect("manage_users")


@admin_required
@require_POST
def reset_user_password(request, user_id):
    target = get_object_or_404(User, pk=user_id)
    new_password = request.POST.get("password", "")
    if len(new_password) < 6:
        messages.error(request, "Password must be at least 6 characters.")
    else:
        target.password = make_password(new_password)
        target.save(update_fields=["password"])
        messages.success(request, f"Password reset for {target.name}.")
    return redirect("manage_users")


@admin_required
def manage_forms(request):
    q = request.GET.get("q", "").strip()
    forms_qs = (Form.objects.select_related("owner__department")
                .annotate(response_count=Count("responses")).order_by("-created_at"))
    if q:
        forms_qs = forms_qs.filter(Q(title__icontains=q) | Q(owner__name__icontains=q))
    return render(request, "manage/forms.html", {
        "me": request.org_user, "forms": forms_qs, "q": q,
    })
def notify_hod_new_request(response):
    hod = response.department.hod if response.department else None
    if not hod or not hod.email:
        return
    requester = response.respondent.name if response.respondent else "An employee"
    link = f"{settings.SITE_URL}/approvals/{response.response_id}/"
    body = (f'{requester} ({response.department.name}) submitted "{response.form.title}" '
            f"and it needs your approval.\n\nReview it here:\n{link}\n")
    try:
        send_mail(f"Approval needed: {response.form.title}", body, None, [hod.email], fail_silently=False)
    except Exception as e:
        print(f"HOD notification failed: {e}")


#def notify_requester_decision(response, decision, comment):
  #  grants = list(response.grants.all())
  #  if grants and decision == "approved":
  #      body += "\n\nFolder access set by your HOD:\n" + "\n".join(
  #          f"- {g.folder_path}: {g.get_level_display()}" for g in grants)
  #  user = response.respondent
  #  if not user or not user.email:
  #      return
  #  verdict = ("approved by your HOD and sent to the IT Manager" if decision == "approved"
   #            else "rejected by your HOD")
   # body = f'Your request "{response.form.title}" was {verdict}.'
    #   if comment:
#        body += f"\n\nComment: {comment}"
#    try:
#        send_mail(f"Request update: {response.form.title}", body, None, [user.email], fail_silently=False)
#    except Exception as e:
 #       print(f"Requester notification failed: {e}")
def notify_requester_decision(response, decision, comment):
    user = response.respondent
    if not user or not user.email:
        return
    verdict = ("approved by your HOD and sent to the IT Manager" if decision == "approved"
               else "rejected by your HOD")
    body = f'Your request "{response.form.title}" was {verdict}.'
    if comment:
        body += f"\n\nComment: {comment}"
    grants = list(response.grants.all())
    if grants and decision == "approved":
        body += "\n\nFolder access set by your HOD:\n" + "\n".join(
            f"- {g.folder_path}: {g.get_level_display()}" for g in grants)
    try:
        send_mail(f"Request update: {response.form.title}", body, None, [user.email], fail_silently=False)
    except Exception as e:
        print(f"Requester notification failed: {e}")

@hod_required
def hod_approvals(request):
    me = request.org_user
    base = (FormResponse.objects.filter(department__hod=me).exclude(respondent=me)
            .select_related("form", "respondent", "department").order_by("-submitted_at"))
    return render(request, "approvals/list.html", {
        "pending": base.filter(status="pending_hod"),
        "decided": base.exclude(status="pending_hod")[:50],
    })



def requested_folders(resp):
    answers = {a.element_id: a for a in resp.answers.select_related("element")}
    paths = []
    fe = resp.form.folders_element_id
    if fe and fe in answers:
        value = answers[fe].value
        paths += value if isinstance(value, list) else [value]
    for a in answers.values():
        el = a.element
        if el.pk == fe:
            continue
        if (el.question_type == "short" and FOLDER_QUESTION.match(el.question_text)
                and a.answer_text.strip()):
            paths.append(a.answer_text.strip())
       
    return [p for p in paths if p]
#def hod_request_detail(request, response_id):
  #  me = request.org_user
  #  resp = get_object_or_404(
  #      FormResponse.objects.select_related("form", "respondent", "department"),
  #      pk=response_id, department__hod=me,
  #  )
  #  answers = {a.element_id: a for a in
   #            resp.answers.select_related("element").prefetch_related("files")}
  #  rows = [{"element": el, "answer": answers.get(el.element_id)}
  #          for el in resp.form.elements.filter(element_type="question")]
  #  return render(request, "approvals/detail.html", {
  #      "resp": resp, "rows": rows,
   #     "logs": resp.approval_logs.select_related("approver"),
   # })
@hod_required
def hod_request_detail(request, response_id):
    me = request.org_user
    resp = get_object_or_404(
        FormResponse.objects.select_related("form", "respondent", "department"),
        pk=response_id, department__hod=me,
    )
    answers = {a.element_id: a for a in
               resp.answers.select_related("element").prefetch_related("files")}
    rows = [{"element": el, "answer": answers.get(el.element_id)}
            for el in resp.form.elements.filter(element_type="question")]
    return render(request, "approvals/detail.html", {
        "resp": resp, "rows": rows,
        "folders": requested_folders(resp) if resp.status == "pending_hod" else [],
        "grants": resp.grants.select_related("set_by"),
        "logs": resp.approval_logs.select_related("approver"),
    })


@hod_required
@require_POST
@transaction.atomic
def hod_decide(request, response_id):
    me = request.org_user
    resp = get_object_or_404(FormResponse.objects.select_related("form", "respondent", "department"),
                             pk=response_id, department__hod=me)
    if resp.respondent_id == me.pk:
        raise PermissionDenied   # nobody approves their own request

    if resp.status != "pending_hod":
        messages.error(request, "This request has already been decided.")
        return redirect("hod_approvals")

    decision = request.POST.get("decision")
    comment = request.POST.get("comment", "").strip()
    if decision not in ("approved", "rejected"):
        return redirect("hod_request_detail", response_id=resp.response_id)
    if decision == "rejected" and not comment:
        messages.error(request, "Please give a reason when rejecting.")
        return redirect("hod_request_detail", response_id=resp.response_id)

    levels = []
    if decision == "approved":
        for i, path in enumerate(requested_folders(resp)):      # folders come from the stored answers
            level = request.POST.get(f"level_{i}", "")
            if level not in ("full", "read"):
                messages.error(request, "Please choose Full Access or Read Only for every folder before approving.")
                return redirect("hod_request_detail", response_id=resp.response_id)
            levels.append((path, level))

    resp.status = "pending_it" if decision == "approved" else "rejected_hod"
    resp.save(update_fields=["status"])
    ApprovalLog.objects.create(response=resp, stage="hod", approver=me,
                               decision=decision, comment=comment)
    for path, level in levels:
        AccessGrant.objects.create(response=resp, folder_path=path[:500], level=level, set_by=me)
    transaction.on_commit(lambda: notify_requester_decision(resp, decision, comment),robust=True)

    messages.success(request, f"Request {decision}.")
    return redirect("hod_approvals")
#def hod_decide(request, response_id):
 #   me = request.org_user
  #  resp = get_object_or_404(FormResponse.objects.select_related("form", "respondent", "department"),
   #                          pk=response_id, department__hod=me)
   # if resp.respondent_id == me.pk:
     #   raise PermissionDenied   # nobody approves their own request

   # if resp.status != "pending_hod":
    #    messages.error(request, "This request has already been decided.")
   #     return redirect("hod_approvals")

  #  decision = request.POST.get("decision")
  #  comment = request.POST.get("comment", "").strip()
  #  if decision not in ("approved", "rejected"):
  #      return redirect("hod_request_detail", response_id=resp.response_id)
  #  if decision == "rejected" and not comment:
  #      messages.error(request, "Please give a reason when rejecting.")
  #      return redirect("hod_request_detail", response_id=resp.response_id)

  #  resp.status = "pending_it" if decision == "approved" else "rejected_hod"
  #  resp.save(update_fields=["status"])
   # ApprovalLog.objects.create(response=resp, stage="hod", approver=me,
  #                             decision=decision, comment=comment)
   # transaction.on_commit(lambda: notify_requester_decision(resp, decision, comment))

   # messages.success(request, f"Request {decision}.")
   # return redirect("hod_approvals")
def available_forms(request):
    uid = request.session.get("user_id")
    user = User.objects.filter(pk=uid).first() if uid else None
    if user is None:
        return redirect("login")

    cond = Q(access_type="restricted", invites__email__iexact=user.email)
    if user.department_id:
        cond |= Q(access_type="departments", departments=user.department_id)

    forms_qs = (Form.objects.filter(is_published=True).filter(cond)
                .exclude(owner=user).select_related("owner").distinct().order_by("-updated_at"))
    return render(request, "available_forms.html", {"forms": forms_qs})
def _login_user(request):
    uid = request.session.get("user_id")
    return User.objects.select_related("department").filter(pk=uid).first() if uid else None


def get_system_form(purpose):
    return Form.objects.filter(purpose=purpose, is_published=True).first()


def _code_verified(request, user):
    ok = request.session.get("asset_code_ok")
    return bool(ok) and ok.get("user") == str(user.pk) and time.time() - ok.get("ts", 0) < 900


def my_assets(request):
    user = _login_user(request)
    if user is None:
        return redirect("login")
    form = get_system_form("asset_access")
    if form is None:
        return redirect("available_forms")
    last = FormResponse.objects.filter(form=form, respondent=user).first()
    if last is None:                                   # new employee: straight to the form
        return redirect("view_form", form_id=form.form_id)
    if _code_verified(request, user):
        return redirect("my_asset_profile")
    return redirect("asset_code_gate")


def asset_code_gate(request):
    user = _login_user(request)
    if user is None:
        return redirect("login")
    if time.time() < request.session.get("code_locked_until", 0):
        return render(request, "asset_code_gate.html", {"locked": True})

    if request.method == "POST":
        typed = request.POST.get("employee_code", "").strip()
        if user.employee_code and typed.lower() == user.employee_code.lower():
            request.session["asset_code_ok"] = {"user": str(user.pk), "ts": time.time()}
            request.session["code_attempts"] = 0
            return redirect("my_asset_profile")
        attempts = request.session.get("code_attempts", 0) + 1
        if attempts >= 5:
            request.session["code_locked_until"] = time.time() + 600
            request.session["code_attempts"] = 0
            return render(request, "asset_code_gate.html", {"locked": True})
        request.session["code_attempts"] = attempts
        messages.error(request, "That employee code doesn't match your account.")

    return render(request, "asset_code_gate.html", {"no_code_on_file": not user.employee_code})
def _profile_context(emp, form, last):
    answers = {a.element_id: a for a in last.answers.select_related("element").prefetch_related("files")}
    items = []
    for el in form.elements.all():
        if el.element_type == "sec":
            items.append({"kind": "section", "title": el.title})
        elif el.element_type == "question":
            a = answers.get(el.element_id)
            if a and (a.answer_text.strip() or a.files.exists()):
                items.append({"kind": "answer", "element": el, "answer": a})
    cleaned = []                                      # drop sections that have no answers
    for i, it in enumerate(items):
        if it["kind"] == "section" and (i + 1 == len(items) or items[i + 1]["kind"] == "section"):
            continue
        cleaned.append(it)
    return {"emp": emp, "form": form, "resp": last, "items": cleaned,
            "logs": last.approval_logs.select_related("approver")}

def my_asset_profile(request):
    user = _login_user(request)
    if user is None:
        return redirect("login")
    form = get_system_form("asset_access")
    if form is None or not _code_verified(request, user):
        return redirect("my_assets")
    last = FormResponse.objects.filter(form=form, respondent=user).order_by("-submitted_at").first()
    if last is None:
        return redirect("my_assets")

    answers = {a.element_id: a for a in last.answers.select_related("element").prefetch_related("files")}
    items = []
    for el in form.elements.all():
        if el.element_type == "sec":
            items.append({"kind": "section", "title": el.title})
        elif el.element_type == "question":
            a = answers.get(el.element_id)
            if a and (a.answer_text.strip() or a.files.exists()):
                items.append({"kind": "answer", "element": el, "answer": a})
    cleaned = []                                       # drop sections that have no answers
    for i, it in enumerate(items):
        if it["kind"] == "section" and (i + 1 == len(items) or items[i + 1]["kind"] == "section"):
            continue
        cleaned.append(it)

    return render(request, "my_asset_profile.html", {
        "emp": user, "form": form, "resp": last, "items": cleaned,
        "logs": last.approval_logs.select_related("approver"),
    })


def folder_request(request):
    if _login_user(request) is None:
        return redirect("login")
    form = get_system_form("folder_request")
    if form is None:
        messages.error(request, "The folder/file request form hasn't been set up yet. Please contact IT.")
        return redirect("available_forms")
    return redirect("view_form", form_id=form.form_id)

@admin_required
def manage_system_forms(request):
    if request.method == "POST":
        asset_val = request.POST.get("asset_access", "")
        folder_val = request.POST.get("folder_request", "")
        if asset_val and asset_val == folder_val:
            messages.error(request, "Choose two different forms.")
            return redirect("manage_system_forms")
        try:
            with transaction.atomic():
                for purpose, raw in (("asset_access", asset_val), ("folder_request", folder_val)):
                    Form.objects.filter(purpose=purpose).update(purpose="", code_element=None)
                    if raw == f"builtin:{purpose}":
                        form = (Form.objects.filter(builtin_key=purpose).first()
                                or create_builtin_form(purpose, request.org_user))
                    else:
                        form = Form.objects.filter(pk=raw).first() if raw else None
                    if form is None:
                        continue
                    form.purpose = purpose
                    form.access_type = "anyone"
                    if purpose == "asset_access":
                        el_id = request.POST.get("code_element", "")
                        chosen = (form.elements.filter(pk=el_id, element_type="question").first()
                                  if el_id else None)
                        form.code_element = chosen or form.elements.filter(
                            element_type="question", question_text="Employee Code").first()
                    else:
                        el_id = request.POST.get("folders_element", "")
                        chosen = (form.elements.filter(pk=el_id, element_type="question",
                                                       question_type="checkbox").first() if el_id else None)
                        form.folders_element = (chosen or form.folders_element or form.elements.filter(
                            element_type="question", question_text="Folders").first())
                    form.save()
                sync_folder_options()
        except ValidationError:
            messages.error(request, "Invalid selection.")
            return redirect("manage_system_forms")
        messages.success(request, "System forms saved.")
        return redirect("manage_system_forms")

    asset_form = Form.objects.filter(purpose="asset_access").first()
    folder_form = Form.objects.filter(purpose="folder_request").first()
    return render(request, "manage/system_forms.html", {
        "all_forms": Form.objects.order_by("title"),
        "asset_form": asset_form,
        "folder_form": folder_form,
        "code_choices": asset_form.elements.filter(element_type="question") if asset_form else [],
        "folder_choices": (folder_form.elements.filter(element_type="question", question_type="checkbox")
                           if folder_form else []),
        "folder_count": SharedFolder.objects.filter(is_active=True).count(),
    })


@admin_required
@require_POST
def set_employee_code(request, user_id):
    target = get_object_or_404(User, pk=user_id)
    code = request.POST.get("employee_code", "").strip() or None
    if code and User.objects.filter(employee_code__iexact=code).exclude(pk=target.pk).exists():
        messages.error(request, "That employee code is already used by another account.")
    else:
        target.employee_code = code
        target.save(update_fields=["employee_code"])
        messages.success(request, f"Employee code updated for {target.name}.")
    return redirect("manage_users")
@admin_required
def manage_folders(request):
    return render(request, "manage/folders.html", {
        "folders": SharedFolder.objects.order_by("path"),
        "form_ready": Form.objects.exclude(folders_element=None).exists(),
    })


@admin_required
@require_POST
def add_folders(request):
    added = 0
    for line in request.POST.get("paths", "").splitlines():
        path = line.strip()[:400]
        if path and not SharedFolder.objects.filter(path__iexact=path).exists():
            SharedFolder.objects.create(path=path)
            added += 1
    sync_folder_options()
    messages.success(request, f"{added} folder(s) added.")
    return redirect("manage_folders")


@admin_required
@require_POST
def toggle_folder(request, folder_id):
    folder = get_object_or_404(SharedFolder, pk=folder_id)
    folder.is_active = not folder.is_active
    folder.save(update_fields=["is_active"])
    sync_folder_options()
    return redirect("manage_folders")


@admin_required
@require_POST
def delete_folder(request, folder_id):
    get_object_or_404(SharedFolder, pk=folder_id).delete()
    sync_folder_options()
    messages.success(request, "Folder removed.")
    return redirect("manage_folders")

@hod_required
def hod_department_requests(request):
    me = request.org_user
    qs = (FormResponse.objects.filter(department__hod=me).exclude(respondent=me)
          .select_related("form", "respondent", "department").order_by("-submitted_at"))
    status = request.GET.get("status", "")
    q = request.GET.get("q", "").strip()
    if status in dict(FormResponse.STATUS_CHOICES):
        qs = qs.filter(status=status)
    if q:
        qs = qs.filter(Q(respondent__name__icontains=q) | Q(respondent__email__icontains=q)
                       | Q(form__title__icontains=q))
    total = qs.count()
    return render(request, "approvals/department_requests.html", {
        "requests_qs": qs[:200], "total": total, "status": status, "q": q,
        "status_choices": FormResponse.STATUS_CHOICES,
    })


@hod_required
def hod_team(request):
    me = request.org_user
    asset_form = Form.objects.filter(purpose="asset_access").first()
    members = (User.objects.filter(department__hod=me).exclude(pk=me.pk)
               .select_related("department").order_by("department__name", "name"))
    latest = {}
    if asset_form:
        for r in (FormResponse.objects.filter(form=asset_form, respondent__in=members)
                  .order_by("submitted_at")):
            latest[r.respondent_id] = r                  # the newest one wins
    rows = [{"user": u, "last": latest.get(u.pk)} for u in members]
    return render(request, "approvals/team.html", {"rows": rows, "asset_form": asset_form})


@hod_required
def hod_employee_profile(request, user_id):
    me = request.org_user
    emp = get_object_or_404(User.objects.select_related("department"),
                            pk=user_id, department__hod=me)          # only your own department
    form = Form.objects.filter(purpose="asset_access").first()
    last = (FormResponse.objects.filter(form=form, respondent=emp).order_by("-submitted_at").first()
            if form else None)
    if last is None:
        messages.error(request, f"{emp.name} hasn't submitted an Assets & Access form yet.")
        return redirect("hod_team")
    ctx = _profile_context(emp, form, last)
    ctx["readonly"] = True
    return render(request, "my_asset_profile.html", ctx)
@admin_required
@require_POST
@transaction.atomic
def delete_user(request, user_id):
    target = get_object_or_404(User, pk=user_id)
    if target.pk == request.org_user.pk:
        messages.error(request, "You can't delete your own account.")
        return redirect("manage_users")

    name = target.name
    owned = Form.objects.filter(owner=target)
    moved = owned.count()
    if moved:                                   # keep their forms (and the responses to them)
        owned.update(owner=request.org_user, owner_name=request.org_user.name)
    headed = list(target.headed_departments.values_list("name", flat=True))

    target.delete()

    note = f"User {name} deleted."
    if moved:
        note += f" {moved} form(s) were transferred to you."
    if headed:
        note += f" No HOD is set now for: {', '.join(headed)}."
    messages.success(request, note)
    return redirect("manage_users")
def _safe_date(value):
    try:
        return parse_date(value) if value else None
    except ValueError:
        return None


def _visible_responses(request):
    qs = FormResponse.objects.select_related("form", "respondent", "department")
    me = request.org_user
    if me.is_admin:
        return qs                                              # admins: everything
    return qs.filter(department__hod=me).exclude(respondent=me)   # HODs: their departments only


@responses_access_required
def responses_list(request):
    base = _visible_responses(request)
    qs = base.order_by("-submitted_at")

    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")
    form_id = request.GET.get("form", "")
    dept_id = request.GET.get("department", "")
    date_from = request.GET.get("from", "")
    date_to = request.GET.get("to", "")

    if q:
        qs = qs.filter(Q(respondent__name__icontains=q) | Q(respondent__email__icontains=q)
                       | Q(respondent__employee_code__icontains=q) | Q(form__title__icontains=q))
    if status in dict(FormResponse.STATUS_CHOICES):
        qs = qs.filter(status=status)
    if form_id:
        try:
            qs = qs.filter(form_id=form_id)
        except ValidationError:
            pass
    if dept_id.isdigit() and request.org_user.is_admin:
        qs = qs.filter(department_id=int(dept_id))
    #if _safe_date(date_from):
        #qs = qs.filter(submitted_at__date__gte=_safe_date(date_from))
    #if _safe_date(date_to):
        #qs = qs.filter(submitted_at__date__lte=_safe_date(date_to))
    
    d_from = _safe_date(date_from)
    if d_from:
        qs = qs.filter(submitted_at__gte=timezone.make_aware(datetime.combine(d_from, dtime.min)))
    d_to = _safe_date(date_to)
    if d_to:
        qs = qs.filter(submitted_at__lt=timezone.make_aware(datetime.combine(d_to + timedelta(days=1), dtime.min)))
    total = qs.count()
    return render(request, "responses/list.html", {
        "responses": qs[:200],
        "total": total,
        "forms": Form.objects.filter(pk__in=base.values("form_id")).order_by("title"),
        "departments": Department.objects.order_by("name"),
        "status_choices": FormResponse.STATUS_CHOICES,
        "q": q, "status": status, "f_form": form_id, "f_dept": dept_id,
        "date_from": date_from, "date_to": date_to,
        "is_admin_view": request.org_user.is_admin,
    })


@responses_access_required
def response_detail(request, response_id):
    me = request.org_user
    resp = get_object_or_404(_visible_responses(request), pk=response_id)
    ctx = _profile_context(resp.respondent, resp.form, resp)
    ctx.update({
        "grants": resp.grants.select_related("set_by"),
        "is_admin_view": me.is_admin,
        "can_decide": (resp.status == "pending_hod" and resp.department_id is not None
                       and resp.department.hod_id == me.pk and resp.respondent_id != me.pk),
    })
    return render(request, "responses/detail.html", ctx)

def _current_record(user, form):
    """The user's current asset record: the newest recorded/approved one, else the newest of any."""
    qs = FormResponse.objects.filter(form=form, respondent=user)
    return (qs.filter(status__in=["recorded", "approved_it"]).order_by("-submitted_at").first()
            or qs.order_by("-submitted_at").first())
def _values_from_answer(el, answer):
    if answer is None:
        return "", [], {}
    v = answer.value
    if el.question_type == "checkbox":
        return "", (v if isinstance(v, list) else []), {}
    if el.question_type in ("mcq_grid", "checkbox_grid"):
        return "", [], (v if isinstance(v, dict) else {})
    return answer.answer_text, [], {}



def _values_from_post(el, post):
    name = f"answer_{el.pk}"
    if el.question_type in ("mcq_grid", "checkbox_grid"):
        grid = {}
        for i, row in enumerate(el.grid_row_list):
            sel = post.getlist(f"{name}__{i}")
            if sel:
                grid[row] = sel if el.question_type == "checkbox_grid" else sel[0]
        return "", [], grid
    if el.question_type == "checkbox":
        return "", post.getlist(name), {}
    return post.get(name, ""), [], {}


def _build_fields(form, getter, defaults, errors):
    fields = []
    for el in form.elements.all():
        if el.element_type in ("sec", "text"):
            fields.append({"kind": "section" if el.element_type == "sec" else "text",
                           "title": el.title, "description": el.description})
            continue
        if el.element_type != "question":
            continue
        text, picked, grid = getter(el)
        if not text and not picked and not grid:
            text = defaults.get(el.question_text.strip(), "")
        qtype = el.question_type
        options = [o.option_text for o in el.options.all()]
        if qtype == "linear_scale":
            options = [str(n) for n in el.scale_range]
        rows = []
        if qtype in ("mcq_grid", "checkbox_grid"):
            for i, label in enumerate(el.grid_row_list):
                sel = grid.get(label)
                sel_list = sel if isinstance(sel, list) else ([sel] if sel else [])
                rows.append({"i": i, "label": label,
                             "cells": [{"col": c, "checked": c in sel_list} for c in options]})
        fields.append({
            "kind": "q", "el": el, "name": f"answer_{el.pk}", "type": qtype, "text": text,
            "options": [{"text": o, "checked": (o in picked) or (o == text)} for o in options],
            "rows": rows, "cols": options,
            "is_code": el.pk == form.code_element_id,
            "error": errors.get(str(el.pk), ""),
        })
    return fields


@admin_required
def manage_assets(request):
    form = Form.objects.filter(purpose="asset_access").first()
    q = request.GET.get("q", "").strip()
    dept = request.GET.get("department", "")
    only_missing = request.GET.get("missing") == "1"

    users = User.objects.select_related("department").order_by("name")
    if q:
        users = users.filter(Q(name__icontains=q) | Q(email__icontains=q) | Q(employee_code__icontains=q))
    if _int_or_none(dept):
        users = users.filter(department_id=int(dept))

    latest = {}
    if form:
        for r in FormResponse.objects.filter(form=form, respondent__in=users).order_by("submitted_at"):
            latest[r.respondent_id] = r                      # the newest one wins
    rows = [{"user": u, "rec": latest.get(u.pk)} for u in users]
    if only_missing:
        rows = [r for r in rows if r["rec"] is None]

    return render(request, "manage/assets.html", {
        "rows": rows, "asset_form": form, "q": q, "f_dept": dept, "only_missing": only_missing,
        "departments": Department.objects.order_by("name"),
    })


@admin_required
def manage_asset_fill(request, user_id):
    target = get_object_or_404(User.objects.select_related("department"), pk=user_id)
    form = Form.objects.filter(purpose="asset_access").first()
    if form is None or not form.code_element_id:
        messages.error(request, "Set the Assets & Access form and its employee-code question under System Forms first.")
        return redirect("manage_system_forms")

    defaults = {
        "Employee Code": target.employee_code or "",
        "Name": target.name,
        "Department": target.department.name if target.department else "",
        "Email ID": target.email,
        "Date": timezone.localdate().isoformat(),
    }
    errors = {}

    if request.method == "POST":
        collected = []
        for el in form.elements.all():
            if el.element_type != "question":
                continue
            stored, uploads, error = validate_answer(el, request.POST, request.FILES)
            # admins may leave anything blank except the employee code
            if error and not (error == "This question is required." and el.pk != form.code_element_id):
                errors[str(el.pk)] = error
            elif stored:
                collected.append((el, stored))

        new_code = next((s.strip() for el, s in collected if el.pk == form.code_element_id), "")
        if not new_code:
            errors[str(form.code_element_id)] = "The employee code is required."
        elif User.objects.filter(employee_code__iexact=new_code).exclude(pk=target.pk).exists():
            errors[str(form.code_element_id)] = "This code already belongs to another user."

        if not errors:
            with transaction.atomic():
                response = FormResponse.objects.create(
                    form=form, respondent=target, department=target.department,
                    status="recorded", entered_by=request.org_user)
                for el, stored in collected:
                    Answer.objects.create(response=response, element=el, answer_text=stored)
                target.employee_code = new_code
                target.save(update_fields=["employee_code"])
            messages.success(request, f"Asset information saved for {target.name}. "
                                      "They only need to enter their employee code after logging in.")
            return redirect("manage_assets")

        getter = lambda el: _values_from_post(el, request.POST)
    else:
        record = _current_record(target, form)
        answers = ({a.element_id: a for a in record.answers.select_related("element")} if record else {})
        getter = lambda el: _values_from_answer(el, answers.get(el.pk))

    return render(request, "manage/asset_fill.html", {
        "target": target, "form": form, "errors": errors,
        "fields": _build_fields(form, getter, defaults, errors),
    })
