import json
from decimal import Decimal, InvalidOperation

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from .models import ApprovalRecord, ProcurementRequest, UserProfile


def index(request):
    return render(request, "index.html")


def register_page(request):
    return render(request, "register.html")


def dashboard(request):
    return render(request, "dashboard.html")


def api_root(request):
    return JsonResponse(
        {
            "message": "Procurement approval API is ready.",
            "endpoints": [
                "/api/register/",
                "/api/login/",
                "/api/logout/",
                "/api/session/",
                "/api/purchases/",
            ],
        }
    )


def _json_body(request):
    try:
        return json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return {}


def _profile_to_dict(profile):
    return {
        "username": profile.user.username,
        "display_name": profile.display_name,
        "role": profile.role,
        "role_label": profile.get_role_display(),
    }


def _record_to_dict(record):
    return {
        "id": record.id,
        "actor": record.actor.profile.display_name,
        "actor_role": record.actor.profile.get_role_display(),
        "action": record.action,
        "action_label": record.get_action_display(),
        "comment": record.comment,
        "created_at": record.created_at.strftime("%Y-%m-%d %H:%M:%S"),
    }


def _timeline_for_user(item, user):
    records = item.approval_records.select_related("actor__profile")
    if user.profile.role in {UserProfile.ROLE_APPLICANT, UserProfile.ROLE_MENTOR}:
        return [_record_to_dict(record) for record in records]
    return [_record_to_dict(record) for record in records if record.actor_id == user.id]


def _request_to_dict(item, user):
    return {
        "id": item.id,
        "item_name": item.item_name,
        "quantity": item.quantity,
        "amount": f"{item.amount:.2f}",
        "purpose": item.purpose,
        "status": item.status,
        "status_label": item.get_status_display(),
        "current_reviewer_role": item.current_reviewer_role,
        "current_reviewer_label": dict(UserProfile.ROLE_CHOICES).get(item.current_reviewer_role, "无需审批"),
        "rejection_reason": item.rejection_reason,
        "submitted_at": item.submitted_at.strftime("%Y-%m-%d %H:%M:%S") if item.submitted_at else "",
        "approved_at": item.approved_at.strftime("%Y-%m-%d %H:%M:%S") if item.approved_at else "",
        "applicant": item.applicant.profile.display_name,
        "applicant_username": item.applicant.username,
        "is_editable": item.can_edit(),
        "timeline": _timeline_for_user(item, user),
    }


def _require_login(request):
    if request.user.is_authenticated:
        return None
    return JsonResponse({"detail": "请先登录。"}, status=401)


def _validate_purchase_payload(payload):
    item_name = (payload.get("item_name") or "").strip()
    purpose = (payload.get("purpose") or "").strip()
    try:
        quantity = int(payload.get("quantity") or 0)
        amount = Decimal(str(payload.get("amount") or "0"))
    except (TypeError, ValueError, InvalidOperation):
        raise ValueError("请填写有效的申请信息。")

    if not item_name or not purpose or quantity <= 0 or amount <= 0:
        raise ValueError("物品、数量、金额和用途必须有效。")

    return {
        "item_name": item_name,
        "quantity": quantity,
        "amount": amount,
        "purpose": purpose,
    }


def _visible_requests_for(user):
    role = user.profile.role
    queryset = ProcurementRequest.objects.select_related("applicant__profile").prefetch_related("approval_records__actor__profile")
    if role == UserProfile.ROLE_APPLICANT:
        return queryset.filter(applicant=user)
    if role == UserProfile.ROLE_FINANCE:
        return queryset.filter(
            Q(current_reviewer_role=UserProfile.ROLE_FINANCE)
            | Q(approval_records__actor=user)
        ).distinct()
    return queryset


@require_http_methods(["POST"])
def register_user(request):
    payload = _json_body(request)
    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""
    display_name = (payload.get("display_name") or "").strip()
    role = payload.get("role") or UserProfile.ROLE_APPLICANT

    if not username or not password or not display_name:
        return JsonResponse({"detail": "用户名、密码和姓名不能为空。"}, status=400)
    if role not in dict(UserProfile.ROLE_CHOICES):
        return JsonResponse({"detail": "角色不合法。"}, status=400)
    if User.objects.filter(username=username).exists():
        return JsonResponse({"detail": "用户名已存在。"}, status=400)

    user = User.objects.create_user(username=username, password=password)
    UserProfile.objects.create(user=user, display_name=display_name, role=role)
    login(request, user)
    return JsonResponse({"user": _profile_to_dict(user.profile)}, status=201)


@require_http_methods(["POST"])
def login_user(request):
    payload = _json_body(request)
    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""
    user = authenticate(request, username=username, password=password)
    if user is None:
        return JsonResponse({"detail": "用户名或密码错误。"}, status=400)
    login(request, user)
    return JsonResponse({"user": _profile_to_dict(user.profile)})


@require_http_methods(["POST"])
def logout_user(request):
    logout(request)
    return JsonResponse({"message": "已退出登录。"})


@require_http_methods(["GET"])
def session_user(request):
    if not request.user.is_authenticated:
        return JsonResponse({"authenticated": False, "user": None})
    return JsonResponse({"authenticated": True, "user": _profile_to_dict(request.user.profile)})


@require_http_methods(["GET", "POST"])
def purchases(request):
    unauthorized = _require_login(request)
    if unauthorized:
        return unauthorized

    if request.method == "GET":
        items = [_request_to_dict(item, request.user) for item in _visible_requests_for(request.user)]
        return JsonResponse({"results": items})

    if request.user.profile.role != UserProfile.ROLE_APPLICANT:
        return JsonResponse({"detail": "只有申请人可以创建采购申请。"}, status=403)

    payload = _json_body(request)
    try:
        cleaned = _validate_purchase_payload(payload)
        item = ProcurementRequest.objects.create(
            applicant=request.user,
            **cleaned,
            status=ProcurementRequest.STATUS_DRAFT,
        )
    except ValueError as exc:
        return JsonResponse({"detail": str(exc)}, status=400)

    return JsonResponse(_request_to_dict(item, request.user), status=201)


def _get_owned_request(user, request_id):
    return ProcurementRequest.objects.select_related("applicant__profile").prefetch_related("approval_records__actor__profile").get(
        id=request_id,
        applicant=user,
    )


def _get_reviewable_request(request_id):
    return ProcurementRequest.objects.select_related("applicant__profile").prefetch_related("approval_records__actor__profile").get(id=request_id)


@require_http_methods(["GET", "PATCH"])
def purchase_detail(request, request_id):
    unauthorized = _require_login(request)
    if unauthorized:
        return unauthorized

    try:
        item = _get_reviewable_request(request_id)
    except ProcurementRequest.DoesNotExist:
        return JsonResponse({"detail": "申请不存在。"}, status=404)

    role = request.user.profile.role
    if role == UserProfile.ROLE_APPLICANT and item.applicant_id != request.user.id:
        return JsonResponse({"detail": "无权查看该申请。"}, status=403)
    if role == UserProfile.ROLE_FINANCE and item.current_reviewer_role != UserProfile.ROLE_FINANCE and not item.approval_records.filter(actor=request.user).exists():
        return JsonResponse({"detail": "无权查看该申请。"}, status=403)

    if request.method == "GET":
        return JsonResponse(_request_to_dict(item, request.user))

    if role != UserProfile.ROLE_APPLICANT or item.applicant_id != request.user.id:
        return JsonResponse({"detail": "只有申请人可以编辑自己的申请。"}, status=403)
    if not item.can_edit():
        return JsonResponse({"detail": "当前状态不可编辑。"}, status=400)

    payload = _json_body(request)
    try:
        cleaned = _validate_purchase_payload(payload)
        item.item_name = cleaned["item_name"]
        item.quantity = cleaned["quantity"]
        item.amount = cleaned["amount"]
        item.purpose = cleaned["purpose"]
        item.save()
    except ValueError as exc:
        return JsonResponse({"detail": str(exc)}, status=400)
    return JsonResponse(_request_to_dict(item, request.user))


@require_http_methods(["POST"])
def submit_purchase(request, request_id):
    unauthorized = _require_login(request)
    if unauthorized:
        return unauthorized

    try:
        item = _get_owned_request(request.user, request_id)
    except ProcurementRequest.DoesNotExist:
        return JsonResponse({"detail": "申请不存在。"}, status=404)

    if not item.can_edit():
        return JsonResponse({"detail": "当前状态不可重复提交。"}, status=400)

    item.submit()
    item.save()
    ApprovalRecord.objects.create(
        procurement_request=item,
        actor=request.user,
        actor_role=request.user.profile.role,
        action=ApprovalRecord.ACTION_SUBMIT,
        comment="提交采购申请",
    )
    return JsonResponse(_request_to_dict(item, request.user))


@require_http_methods(["POST"])
def approve_purchase(request, request_id):
    unauthorized = _require_login(request)
    if unauthorized:
        return unauthorized

    if request.user.profile.role not in {UserProfile.ROLE_FINANCE, UserProfile.ROLE_MENTOR}:
        return JsonResponse({"detail": "当前角色不能审批。"}, status=403)

    try:
        item = _get_reviewable_request(request_id)
    except ProcurementRequest.DoesNotExist:
        return JsonResponse({"detail": "申请不存在。"}, status=404)

    try:
        item.advance(request.user)
    except ValueError as exc:
        return JsonResponse({"detail": str(exc)}, status=400)

    item.save()
    ApprovalRecord.objects.create(
        procurement_request=item,
        actor=request.user,
        actor_role=request.user.profile.role,
        action=ApprovalRecord.ACTION_APPROVE,
        comment="审批通过",
    )
    return JsonResponse(_request_to_dict(item, request.user))


@require_http_methods(["POST"])
def reject_purchase(request, request_id):
    unauthorized = _require_login(request)
    if unauthorized:
        return unauthorized

    if request.user.profile.role not in {UserProfile.ROLE_FINANCE, UserProfile.ROLE_MENTOR}:
        return JsonResponse({"detail": "当前角色不能审批。"}, status=403)

    try:
        item = _get_reviewable_request(request_id)
    except ProcurementRequest.DoesNotExist:
        return JsonResponse({"detail": "申请不存在。"}, status=404)

    if request.user.profile.role != item.current_reviewer_role:
        return JsonResponse({"detail": "当前用户无权打回该申请。"}, status=400)

    payload = _json_body(request)
    reason = payload.get("reason") or ""
    try:
        item.reject(reason)
    except ValueError as exc:
        return JsonResponse({"detail": str(exc)}, status=400)

    item.save()
    ApprovalRecord.objects.create(
        procurement_request=item,
        actor=request.user,
        actor_role=request.user.profile.role,
        action=ApprovalRecord.ACTION_REJECT,
        comment=item.rejection_reason,
    )
    return JsonResponse(_request_to_dict(item, request.user))
