import django.db.models.deletion
from django.db import migrations, models

DEPARTMENTS = {
    "F": "Finance", "HR": "HR", "Ink": "Ink Store", "It": "IT",
    "Maintain": "Maintenance", "Product": "Production",
    "Sales": "Sales", "Store": "Store",
}

def copy_departments(apps, schema_editor):
    User = apps.get_model("forms", "User")
    Department = apps.get_model("forms", "Department")
    for code, name in DEPARTMENTS.items():
        dept, _ = Department.objects.get_or_create(name=name)
        User.objects.filter(department_name=code).update(department=dept)


class Migration(migrations.Migration):
    dependencies = [("forms", "0012_user_role")]

    operations = [
        migrations.CreateModel(
            name="Department",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("hod", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="headed_departments", to="forms.user")),
            ],
        ),
        migrations.RenameField("user", "department", "department_name"),
        migrations.AddField("user", "department", models.ForeignKey(
            blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
            related_name="members", to="forms.department")),
        migrations.RunPython(copy_departments, migrations.RunPython.noop),
        migrations.RemoveField("user", "department_name"),
    ]