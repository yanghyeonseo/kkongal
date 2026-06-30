from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    model = User

    list_display = (
        "id",
        "username",
        "email",
        "age",
        "job",
        "gender",
        "is_staff",
        "is_active",
        "created_at",
    )

    search_fields = (
        "username",
        "email",
        "job",
        "gender",
    )

    ordering = ("id",)

    fieldsets = UserAdmin.fieldsets + (
        (
            "Additional Info",
            {
                "fields": (
                    "age",
                    "job",
                    "gender",
                    "created_at",
                )
            },
        ),
    )

    add_fieldsets = UserAdmin.add_fieldsets + (
        (
            "Additional Info",
            {
                "fields": (
                    "email",
                    "age",
                    "job",
                    "gender",
                    "created_at",
                )
            },
        ),
    )