from django.db import models
from django.conf import settings
import uuid
import json,os
# Create your models here.
class Department(models.Model):
    name = models.CharField(max_length=100, unique=True)
    hod = models.ForeignKey(
        "forms.User", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="headed_departments",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name
class User(models.Model):
    ROLE_CHOICES = [
        ("admin", "Admin"),
        ("user", "User"),
    ]
    employee_code = models.CharField(max_length=50, null=True, blank=True, unique=True)
    user_id= models.UUIDField(default=uuid.uuid1,primary_key=True,unique=True);
    name=models.CharField(max_length=200);
    password=models.CharField(max_length=200,blank=False);
    email=models.CharField(max_length=250,blank=False);
    department = models.ForeignKey(
        Department, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="members",
    )
    role=models.CharField(max_length=10,choices=ROLE_CHOICES,default='user')


    
    @property
    def is_admin(self):
        return self.role == "admin"
    def __str__(self):
        return self.name

class SharedFolder(models.Model):
    path = models.CharField(max_length=400, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["path"]

    def __str__(self):
        return self.path


class Form(models.Model):
    PURPOSE_CHOICES = [
        ("", "Normal form"),
        ("asset_access", "Assets & Access Management"),
        ("folder_request", "Folder / File request"),
    ]
    builtin_key = models.CharField(max_length=30, blank=True, default="")
    folders_element = models.ForeignKey("FormElement", null=True, blank=True,
                                        on_delete=models.SET_NULL, related_name="+")
    purpose = models.CharField(max_length=20, choices=PURPOSE_CHOICES, blank=True, default="")
    code_element = models.ForeignKey("FormElement", null=True, blank=True,
                                     on_delete=models.SET_NULL, related_name="+")

    form_id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )

    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="forms"
    )
    
    owner_name = models.CharField(
        max_length=200,
        blank=True
    )
    title = models.CharField(
        max_length=250,
        default="Untitled Form"
    )

    description = models.TextField(
        blank=True
    )

    is_published = models.BooleanField(
        default=False
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )
    access_type = models.CharField(
        max_length=20,
        choices=[('anyone', 'Anyone with the link'), ('restricted', 'Restricted'),('departments', 'Selected departments'),
],
        default='anyone'
    )
    departments = models.ManyToManyField(Department, blank=True, related_name="shared_forms")

    def __str__(self):
        return self.title

class FormInvite(models.Model):
    PERMISSION_CHOICES = [
        ("respond", "Can respond"),
        ("edit", "Can edit"),
        ("both", "Can edit and respond"),
    ]
    invite_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    form = models.ForeignKey(Form, on_delete=models.CASCADE, related_name='invites')
    email = models.EmailField()
    permission = models.CharField(max_length=10, choices=PERMISSION_CHOICES, default="respond")
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('form', 'email')
    @property
    def can_edit(self):
        return self.permission in ("edit", "both")

    @property
    def can_respond(self):
        return self.permission in ("respond", "both")

class Question(models.Model):

    QUESTION_TYPES = [
        ("short", "Short answer"),
        ("long", "Long answer"),
        ("multiple", "Multiple choice"),
        ("checkbox", "Checkboxes"),
        ("dropdown", "Dropdown"),
        ("date", "Date"),
        ("file", "File upload"),
    ]

    question_id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )

    form = models.ForeignKey(
        Form,
        on_delete=models.CASCADE,
        related_name="questions"
    )

    question_text = models.CharField(
        max_length=500
    )

    question_type = models.CharField(
        max_length=20,
        choices=QUESTION_TYPES,
        default="short"
    )

    description = models.TextField(
        blank=True
    )

    is_required = models.BooleanField(
        default=False
    )

    order = models.PositiveIntegerField(
        default=0
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return self.question_text


class Option(models.Model):

    option_id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )

    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name="options"
    )
    form = models.ForeignKey(
        Form,
        on_delete=models.CASCADE,
        related_name="options",
        null=True,
        blank=True
    )

    option_text = models.CharField(
        max_length=250
    )

    order = models.PositiveIntegerField(
        default=0
    )

    def __str__(self):
        return self.option_text


class Response(models.Model):
    STATUS_CHOICES = [
        ("pending_hod", "Pending HOD approval"),
        ("rejected_hod", "Rejected by HOD"),
        ("pending_it", "Approved by HOD - pending IT Manager"),
    ]
    department = models.ForeignKey(
        Department, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="requests",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending_hod")

    response_id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )

    form = models.ForeignKey(
        Form,
        on_delete=models.CASCADE,
        related_name="responses"
    )

    respondent = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="responses"
    )

    submitted_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return f"Response to {self.form.title}"

class ApprovalLog(models.Model):
    STAGE_CHOICES = [("hod", "HOD"), ("it", "IT Manager")]
    DECISION_CHOICES = [("approved", "Approved"), ("rejected", "Rejected")]

    response = models.ForeignKey(Response, on_delete=models.CASCADE, related_name="approval_logs")
    stage = models.CharField(max_length=10, choices=STAGE_CHOICES)
    approver = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name="approvals_given")
    decision = models.CharField(max_length=10, choices=DECISION_CHOICES)
    comment = models.TextField(blank=True)
    decided_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["decided_at"]
#class Answer(models.Model):

 #   answer_id = models.UUIDField(
  #      primary_key=True,
   #     default=uuid.uuid4,
   #     editable=False
   # )

class AccessGrant(models.Model):
    LEVEL_CHOICES = [("full", "Full Access"), ("read", "Read Only")]

    response = models.ForeignKey(Response, on_delete=models.CASCADE, related_name="grants")
    folder_path = models.CharField(max_length=500)
    level = models.CharField(max_length=10, choices=LEVEL_CHOICES)
    set_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "folder_path"]
class Answer(models.Model):

    JSON_TYPES = ("checkbox", "mcq_grid", "checkbox_grid")

    answer_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    response = models.ForeignKey(
        Response, on_delete=models.CASCADE, related_name="answers"
    )

    # FormElement is defined further down the file, so it's referenced by name.
    # null=True only lets the migration run without asking for a default.
    element = models.ForeignKey(
        "FormElement", on_delete=models.CASCADE, related_name="answers", null=True
    )

    # plain text for most types; JSON for checkbox / grids
    answer_text = models.TextField(blank=True)

    @property
    def value(self):
        """The answer as a Python value (list for checkbox, dict for grids)."""
        if self.element and self.element.question_type in self.JSON_TYPES and self.answer_text:
            try:
                return json.loads(self.answer_text)
            except ValueError:
                pass
        return self.answer_text

    @property
    def grid_pairs(self):
        """[(row_label, chosen_value_or_list), ...] for grid answers."""
        v = self.value
        return list(v.items()) if isinstance(v, dict) else []

    def __str__(self):
        return f"Answer {self.answer_id}"


class AnswerFile(models.Model):

    file_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    answer = models.ForeignKey(Answer, on_delete=models.CASCADE, related_name="files")
    file = models.FileField(upload_to="form_answers/")

    @property
    def filename(self):
        return os.path.basename(self.file.name)


class FormElement(models.Model):

    ELEMENT_TYPES = [
        ("question", "Question"),
        ("text", "Text/Description"),
        ("image", "Image"),
        ("sec", "Section"),
        
    ]

    QUESTION_TYPES = [
        ("short", "Short answer"),
        ("paragraph", "Paragraph"),
        ("mcq", "Multiple choice"),
        ("checkbox", "Checkboxes"),
        ("dropdown", "Dropdown"),
        ("file_upload", "File upload"),
        ("linear_scale", "Linear scale"),
        ("mcq_grid", "Multiple-choice grid"),
        ("checkbox_grid", "Checkbox grid"),
        ("date", "Date"),
        ("time", "Time"),
    ]

    element_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    form = models.ForeignKey(Form, on_delete=models.CASCADE, related_name="elements")
    order = models.PositiveIntegerField()
    element_type = models.CharField(max_length=20, choices=ELEMENT_TYPES)

    # question-type fields
    question_text = models.CharField(max_length=1000, blank=True)
    question_type = models.CharField(max_length=20, choices=QUESTION_TYPES, blank=True)

    # text/sec-type fields
    title = models.CharField(max_length=500, blank=True)
    description = models.TextField(blank=True)

    # image-type field
    image = models.ImageField(upload_to="form_images/", null=True, blank=True)

    scale_min = models.PositiveIntegerField(null=True, blank=True)
    scale_max = models.PositiveIntegerField(null=True, blank=True)
    scale_min_label = models.CharField(max_length=100, blank=True)
    scale_max_label = models.CharField(max_length=100, blank=True)

    # grid config — rows stored newline-separated; columns reuse ElementOption
    grid_rows = models.TextField(blank=True)

    # file upload config
    max_files = models.PositiveIntegerField(default=1)

    is_required = models.BooleanField(default=False)

    class Meta:
        ordering = ["order"]
    @property
    def grid_row_list(self):
        return [r.strip() for r in self.grid_rows.splitlines() if r.strip()]

    @property
    def scale_range(self):
        lo = self.scale_min if self.scale_min is not None else 1
        hi = self.scale_max if self.scale_max is not None else 5
        return range(lo, hi + 1)

class ElementOption(models.Model):
    option_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    element = models.ForeignKey(FormElement, on_delete=models.CASCADE, related_name="options")
    option_text = models.CharField(max_length=500)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order"]