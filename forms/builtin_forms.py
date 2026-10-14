from django.db import transaction
from .models import Form, FormElement, ElementOption, SharedFolder


def S(title, desc=""):
    return {"t": "sec", "title": title, "desc": desc}


def T(title, desc=""):
    return {"t": "text", "title": title, "desc": desc}


def Q(text, qtype="short", req=False, options=None, rows=None, key=None):
    return {"t": "q", "text": text, "type": qtype, "req": req,
            "options": options or [], "rows": rows or [], "key": key}


ASSET_SPEC = [
    T("Assets & Access Management",
      "A Manager or HOD (Custodian) must approve this form to request access & assets for their employee. "
      "Your request goes to your HOD first, then to the IT Manager."),

    S("Part 1: Employee Information"),
    Q("Employee Code", req=True, key="code"),
    Q("Name", req=True),
    Q("Department", req=True),
    Q("Date", "date", req=True),

    S("Part 2: Asset Information"),
    Q("Windows User ID"),
    Q("Email ID"),
    Q("Track ID"), Q("Model #"), Q("Serial #"), Q("Core - Gen"), Q("RAM"), Q("SSD/HDD"),
    Q("Accessories", "checkbox", options=["Bag", "Mouse", "Charger"]),
    Q("MAC ID # 1"), Q("MAC ID # 2"), Q("MAC ID # 3"),
    Q("Cellular MAC 1"), Q("Cellular MAC 2"),

    S("Part 3: Access",
      "Please indicate for which applications, shares and environments you are requesting access. "
      "If role-based access exists, please identify the role requested."),
    Q("Application", "checkbox", options=["ERP (Universal)", "SAP"]),
    Q("ERP User ID"), Q("ERP License Type"), Q("SAP User ID"), Q("SAP License Type"),
    Q("Internet Access", "mcq_grid", rows=["Laptop / Desktop", "Cellular"],
      options=["Restricted", "Office Executive", "Learner", "Executive"]),

    S("Sharing / NAS Drive Access",
      "Folder name "
      "For other folders or files, use Request Folder / File in the menu."),
] + [Q(f"Folder {i} - name with complete path") for i in range(1, 8)] + [
   # Q("Accessibility", "mcq_grid", rows=[f"Folder {i}" for i in range(1, 8)],
  #    options=["Full Access", "Read Only"]),

    S("Confirmation"),
    Q("I confirm that the information above is correct and I am requesting the assets and access listed.",
      "checkbox", req=True, options=["I confirm"]),

    T("Part 4: Approval",
      "Your HOD / supervisor and then the IT Manager will review this request online. "
      "You will be notified by email."),
]

FOLDER_SPEC = [
    T("Folder / File Access Request",
      "Select the folder(s) you need and write the file name if your request is about a specific file. "
      "Your request goes to your HOD first, then to the IT Manager."),
    Q("File name (Write complete path of file, e.g. \\10.1.5.55\Common Sharing\Attendence Records\October Attendence..xlsx)"),
    Q("Folders", "checkbox", req=True, key="folders"),
  #  Q("Access level", "mcq", req=True, options=["Full Access", "Read Only"]),
    Q("Reason for request", "paragraph", req=True),
]

BUILTINS = {
    "asset_access": ("Assets & Access Management",
                     "Kompass Pakistan - Assets & Access Management", ASSET_SPEC),
    "folder_request": ("Folder / File Request",
                       "Request access to a shared folder or file.", FOLDER_SPEC),
}


def sync_folder_options():
    """Make the 'Folders' question of every folder form mirror the admin's active folders."""
    paths = list(SharedFolder.objects.filter(is_active=True).order_by("path")
                 .values_list("path", flat=True))
    for form in Form.objects.exclude(folders_element=None).select_related("folders_element"):
        element = form.folders_element
        element.options.all().delete()
        for i, path in enumerate(paths):
            ElementOption.objects.create(element=element, option_text=path, order=i)


@transaction.atomic
def create_builtin_form(purpose, owner):
    title, desc, spec = BUILTINS[purpose]
    form = Form.objects.create(
        owner=owner, owner_name=owner.name, title=title, description=desc,
        is_published=True, access_type="anyone", purpose=purpose, builtin_key=purpose,
    )
    keyed = {}
    for order, item in enumerate(spec):
        if item["t"] == "q":
            el = FormElement.objects.create(
                form=form, order=order, element_type="question",
                question_text=item["text"], question_type=item["type"],
                is_required=item["req"], grid_rows="\n".join(item["rows"]),
            )
            for i, opt in enumerate(item["options"]):
                ElementOption.objects.create(element=el, option_text=opt, order=i)
            if item["key"]:
                keyed[item["key"]] = el
        else:
            FormElement.objects.create(form=form, order=order, element_type=item["t"],
                                       title=item["title"], description=item["desc"])
    form.code_element = keyed.get("code")
    form.folders_element = keyed.get("folders")
    form.save()
    sync_folder_options()
    return form