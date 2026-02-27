from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = (
        "username",
        "email",
        "first_name",
        "last_name",
        "is_main",
        "is_staff",
        "is_active",
        "balance",
        "loan_request_amount",
        "date_joined",
    )
    list_filter = (
        "is_main",
        "is_staff",
        "is_superuser",
        "is_active",
        "date_joined",
    )
    search_fields = (
        "username",
        "email",
        "first_name",
        "last_name",
    )
    readonly_fields = (
        "date_joined",
        "last_login",
    )
    ordering = ("username",)
    fieldsets = UserAdmin.fieldsets + (
        (
            "Fund Info",
            {
                "fields": (
                    "balance",
                    "is_main",
                    "loan_request_amount",
                )
            },
        ),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        (
            "Fund Info",
            {
                "fields": (
                    "balance",
                    "is_main",
                    "loan_request_amount",
                )
            },
        ),
    )
