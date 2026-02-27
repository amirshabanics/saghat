from django.contrib import admin

from .models import Config, LoanPayment, MembershipFeePayment, Payment


@admin.register(Config)
class ConfigAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "min_membership_fee",
        "max_month_for_loan_payment",
        "min_amount_for_loan_payment",
    )
    # Config is a singleton; no search or filter needed


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "amount",
        "jalali_year",
        "jalali_month",
        "bitpin_payment_id",
        "created_at",
    )
    list_filter = (
        "jalali_year",
        "jalali_month",
        "created_at",
    )
    search_fields = (
        "user__username",
        "user__email",
        "bitpin_payment_id",
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


@admin.register(MembershipFeePayment)
class MembershipFeePaymentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "payment",
        "amount",
    )
    search_fields = (
        "payment__user__username",
        "payment__user__email",
        "payment__bitpin_payment_id",
    )
    readonly_fields = ("id",)
    ordering = ("-payment__created_at",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return True


@admin.register(LoanPayment)
class LoanPaymentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "payment",
        "loan",
        "amount",
    )
    list_filter = ("loan",)
    search_fields = (
        "payment__user__username",
        "payment__user__email",
        "payment__bitpin_payment_id",
    )
    readonly_fields = ("id",)
    ordering = ("-payment__created_at",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return True
