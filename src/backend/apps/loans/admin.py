from django.contrib import admin

from .models import Loan


@admin.register(Loan)
class LoanAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "state",
        "amount",
        "jalali_year",
        "jalali_month",
        "min_amount_for_each_payment",
        "created_at",
    )
    list_filter = (
        "state",
        "jalali_year",
        "jalali_month",
        "created_at",
    )
    search_fields = (
        "user__username",
        "user__email",
    )
    readonly_fields = (
        "id",
        "created_at",
    )
    ordering = ("-created_at",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return True
