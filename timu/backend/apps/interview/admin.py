from django.contrib import admin

from .models import ApprovalRecord, ProcurementRequest, UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("display_name", "user", "role")
    list_filter = ("role",)
    search_fields = ("display_name", "user__username")


class ApprovalRecordInline(admin.TabularInline):
    model = ApprovalRecord
    extra = 0
    readonly_fields = ("actor", "actor_role", "action", "comment", "created_at")


@admin.register(ProcurementRequest)
class ProcurementRequestAdmin(admin.ModelAdmin):
    list_display = ("item_name", "applicant", "amount", "status", "current_reviewer_role", "updated_at")
    list_filter = ("status", "current_reviewer_role")
    search_fields = ("item_name", "applicant__username", "applicant__profile__display_name")
    inlines = [ApprovalRecordInline]


@admin.register(ApprovalRecord)
class ApprovalRecordAdmin(admin.ModelAdmin):
    list_display = ("procurement_request", "actor", "actor_role", "action", "created_at")
    list_filter = ("action", "actor_role")
