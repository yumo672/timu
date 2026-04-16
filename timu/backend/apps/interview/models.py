from decimal import Decimal

from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


class UserProfile(models.Model):
    ROLE_APPLICANT = "applicant"
    ROLE_FINANCE = "finance"
    ROLE_MENTOR = "mentor"
    ROLE_CHOICES = [
        (ROLE_APPLICANT, "申请人"),
        (ROLE_FINANCE, "财务专员"),
        (ROLE_MENTOR, "导师"),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    display_name = models.CharField(max_length=64)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_APPLICANT)

    def __str__(self):
        return f"{self.display_name} ({self.get_role_display()})"


class ProcurementRequest(models.Model):
    STATUS_DRAFT = "draft"
    STATUS_PENDING = "pending"
    STATUS_IN_REVIEW = "in_review"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "待提交"),
        (STATUS_PENDING, "待审批"),
        (STATUS_IN_REVIEW, "审批中"),
        (STATUS_APPROVED, "已通过"),
        (STATUS_REJECTED, "已打回"),
    ]

    applicant = models.ForeignKey(User, on_delete=models.CASCADE, related_name="procurement_requests")
    item_name = models.CharField(max_length=120)
    quantity = models.PositiveIntegerField()
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    purpose = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    current_reviewer_role = models.CharField(max_length=20, blank=True, default="")
    rejection_reason = models.TextField(blank=True, default="")
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "-id"]

    def __str__(self):
        return f"{self.item_name} - {self.applicant.username}"

    def review_flow(self):
        if self.amount < Decimal("1000"):
            return []
        if self.amount < Decimal("5000"):
            return [UserProfile.ROLE_FINANCE]
        return [UserProfile.ROLE_FINANCE, UserProfile.ROLE_MENTOR]

    def can_edit(self):
        return self.status in {self.STATUS_DRAFT, self.STATUS_REJECTED}

    def submit(self):
        flow = self.review_flow()
        self.submitted_at = timezone.now()
        self.rejection_reason = ""
        if not flow:
            self.status = self.STATUS_APPROVED
            self.current_reviewer_role = ""
            self.approved_at = timezone.now()
        else:
            self.status = self.STATUS_PENDING
            self.current_reviewer_role = flow[0]
            self.approved_at = None

    def advance(self, approver):
        flow = self.review_flow()
        if approver.profile.role != self.current_reviewer_role:
            raise ValueError("当前用户无权审批该申请。")

        current_index = flow.index(approver.profile.role)
        next_index = current_index + 1
        if next_index >= len(flow):
            self.status = self.STATUS_APPROVED
            self.current_reviewer_role = ""
            self.approved_at = timezone.now()
        else:
            self.status = self.STATUS_IN_REVIEW
            self.current_reviewer_role = flow[next_index]
            self.approved_at = None

    def reject(self, reason):
        if not reason.strip():
            raise ValueError("打回时必须填写理由。")
        self.status = self.STATUS_REJECTED
        self.current_reviewer_role = ""
        self.rejection_reason = reason.strip()
        self.approved_at = None


class ApprovalRecord(models.Model):
    ACTION_SUBMIT = "submit"
    ACTION_APPROVE = "approve"
    ACTION_REJECT = "reject"
    ACTION_CHOICES = [
        (ACTION_SUBMIT, "提交"),
        (ACTION_APPROVE, "通过"),
        (ACTION_REJECT, "打回"),
    ]

    procurement_request = models.ForeignKey(
        ProcurementRequest,
        on_delete=models.CASCADE,
        related_name="approval_records",
    )
    actor = models.ForeignKey(User, on_delete=models.CASCADE, related_name="approval_records")
    actor_role = models.CharField(max_length=20)
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    comment = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"{self.procurement_request_id} - {self.action}"
