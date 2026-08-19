from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import EmailVerification, Interest, User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    model = User

    list_display = (
        "id",
        "email",
        "nickname",
        "email_verified",
        "age",
        "job",
        "gender",
        "is_staff",
        "is_active",
        "created_at",
    )

    search_fields = (
        "email",
        "nickname",
        "username",
        "job",
        "gender",
    )

    list_filter = UserAdmin.list_filter + ("email_verified",)

    ordering = ("id",)

    fieldsets = UserAdmin.fieldsets + (
        (
            "Additional Info",
            {
                "fields": (
                    "nickname",
                    "email_verified",
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
                    "nickname",
                    "age",
                    "job",
                    "gender",
                    "created_at",
                )
            },
        ),
    )


@admin.register(Interest)
class InterestAdmin(admin.ModelAdmin):
    list_display = ("id", "user_id", "keyword", "priority", "created_at")
    list_filter = ("priority", "created_at")
    search_fields = ("keyword", "description", "user_id__email")
    ordering = ("-created_at",)


@admin.register(EmailVerification)
class EmailVerificationAdmin(admin.ModelAdmin):
    """이메일 인증 토큰. 원문 토큰은 저장하지 않으므로 여기서도 볼 수 없다(해시만)."""

    list_display = ("id", "user", "email", "created_at", "expires_at", "used_at")
    list_filter = ("created_at", "expires_at")
    search_fields = ("email", "user__email")
    ordering = ("-created_at",)
    readonly_fields = ("token_hash",)
