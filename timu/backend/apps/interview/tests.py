from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase

from .models import ProcurementRequest, UserProfile


class ProcurementWorkflowTests(TestCase):
    def setUp(self):
        self.applicant = self._create_user("applicant", "申请人", UserProfile.ROLE_APPLICANT)
        self.finance = self._create_user("finance", "财务", UserProfile.ROLE_FINANCE)
        self.mentor = self._create_user("mentor", "导师", UserProfile.ROLE_MENTOR)

    def _create_user(self, username, display_name, role):
        user = User.objects.create_user(username=username, password="pass1234")
        UserProfile.objects.create(user=user, display_name=display_name, role=role)
        return user

    def _draft_request(self, amount):
        return ProcurementRequest.objects.create(
            applicant=self.applicant,
            item_name="办公用品",
            quantity=2,
            amount=Decimal(amount),
            purpose="团队采购",
        )

    def test_amount_below_1000_auto_approved(self):
        self.client.login(username="applicant", password="pass1234")
        request_item = self._draft_request("999.99")

        response = self.client.post(f"/api/purchases/{request_item.id}/submit/")

        self.assertEqual(response.status_code, 200)
        request_item.refresh_from_db()
        self.assertEqual(request_item.status, ProcurementRequest.STATUS_APPROVED)
        self.assertEqual(request_item.current_reviewer_role, "")

    def test_mid_amount_goes_to_finance(self):
        self.client.login(username="applicant", password="pass1234")
        request_item = self._draft_request("3200.00")

        response = self.client.post(f"/api/purchases/{request_item.id}/submit/")

        self.assertEqual(response.status_code, 200)
        request_item.refresh_from_db()
        self.assertEqual(request_item.status, ProcurementRequest.STATUS_PENDING)
        self.assertEqual(request_item.current_reviewer_role, UserProfile.ROLE_FINANCE)

        self.client.logout()
        self.client.login(username="finance", password="pass1234")
        approve_response = self.client.post(f"/api/purchases/{request_item.id}/approve/")
        self.assertEqual(approve_response.status_code, 200)
        request_item.refresh_from_db()
        self.assertEqual(request_item.status, ProcurementRequest.STATUS_APPROVED)

    def test_high_amount_requires_finance_then_mentor(self):
        self.client.login(username="applicant", password="pass1234")
        request_item = self._draft_request("6000.00")
        self.client.post(f"/api/purchases/{request_item.id}/submit/")

        self.client.logout()
        self.client.login(username="finance", password="pass1234")
        finance_response = self.client.post(f"/api/purchases/{request_item.id}/approve/")
        self.assertEqual(finance_response.status_code, 200)
        request_item.refresh_from_db()
        self.assertEqual(request_item.status, ProcurementRequest.STATUS_IN_REVIEW)
        self.assertEqual(request_item.current_reviewer_role, UserProfile.ROLE_MENTOR)

        self.client.logout()
        self.client.login(username="mentor", password="pass1234")
        mentor_response = self.client.post(f"/api/purchases/{request_item.id}/approve/")
        self.assertEqual(mentor_response.status_code, 200)
        request_item.refresh_from_db()
        self.assertEqual(request_item.status, ProcurementRequest.STATUS_APPROVED)

    def test_reject_requires_reason_and_allows_resubmit(self):
        self.client.login(username="applicant", password="pass1234")
        request_item = self._draft_request("1800.00")
        self.client.post(f"/api/purchases/{request_item.id}/submit/")

        self.client.logout()
        self.client.login(username="finance", password="pass1234")
        empty_reason_response = self.client.post(
            f"/api/purchases/{request_item.id}/reject/",
            data='{"reason": ""}',
            content_type="application/json",
        )
        self.assertEqual(empty_reason_response.status_code, 400)

        reject_response = self.client.post(
            f"/api/purchases/{request_item.id}/reject/",
            data='{"reason": "预算说明不完整"}',
            content_type="application/json",
        )
        self.assertEqual(reject_response.status_code, 200)
        request_item.refresh_from_db()
        self.assertEqual(request_item.status, ProcurementRequest.STATUS_REJECTED)
        self.assertEqual(request_item.rejection_reason, "预算说明不完整")

        self.client.logout()
        self.client.login(username="applicant", password="pass1234")
        patch_response = self.client.patch(
            f"/api/purchases/{request_item.id}/",
            data='{"item_name":"办公用品","quantity":2,"amount":"2000.00","purpose":"补充预算说明"}',
            content_type="application/json",
        )
        self.assertEqual(patch_response.status_code, 200)

        resubmit_response = self.client.post(f"/api/purchases/{request_item.id}/submit/")
        self.assertEqual(resubmit_response.status_code, 200)
        request_item.refresh_from_db()
        self.assertEqual(request_item.status, ProcurementRequest.STATUS_PENDING)
        self.assertEqual(request_item.current_reviewer_role, UserProfile.ROLE_FINANCE)

    def test_finance_cannot_view_unrelated_applicant_detail(self):
        self.client.login(username="applicant", password="pass1234")
        request_item = self._draft_request("800.00")

        self.client.logout()
        self.client.login(username="finance", password="pass1234")
        response = self.client.get(f"/api/purchases/{request_item.id}/")

        self.assertEqual(response.status_code, 403)

    def test_approver_timeline_only_contains_their_own_actions(self):
        self.client.login(username="applicant", password="pass1234")
        request_item = self._draft_request("6000.00")
        self.client.post(f"/api/purchases/{request_item.id}/submit/")

        self.client.logout()
        self.client.login(username="finance", password="pass1234")
        self.client.post(f"/api/purchases/{request_item.id}/approve/")
        finance_detail_response = self.client.get(f"/api/purchases/{request_item.id}/")
        self.assertEqual(finance_detail_response.status_code, 200)
        finance_timeline = finance_detail_response.json()["timeline"]
        self.assertEqual(len(finance_timeline), 1)
        self.assertEqual(finance_timeline[0]["actor"], self.finance.profile.display_name)

        self.client.logout()
        self.client.login(username="mentor", password="pass1234")
        self.client.post(f"/api/purchases/{request_item.id}/approve/")

        self.client.logout()
        self.client.login(username="finance", password="pass1234")
        finance_after_mentor_response = self.client.get(f"/api/purchases/{request_item.id}/")
        self.assertEqual(finance_after_mentor_response.status_code, 200)
        finance_after_mentor_timeline = finance_after_mentor_response.json()["timeline"]
        self.assertEqual(len(finance_after_mentor_timeline), 1)
        self.assertEqual(finance_after_mentor_timeline[0]["actor"], self.finance.profile.display_name)

    def test_mentor_can_view_complete_timeline(self):
        self.client.login(username="applicant", password="pass1234")
        request_item = self._draft_request("6000.00")
        self.client.post(f"/api/purchases/{request_item.id}/submit/")

        self.client.logout()
        self.client.login(username="finance", password="pass1234")
        self.client.post(f"/api/purchases/{request_item.id}/approve/")

        self.client.logout()
        self.client.login(username="mentor", password="pass1234")
        mentor_detail_response = self.client.get(f"/api/purchases/{request_item.id}/")

        self.assertEqual(mentor_detail_response.status_code, 200)
        mentor_timeline = mentor_detail_response.json()["timeline"]
        self.assertEqual(len(mentor_timeline), 2)
        self.assertEqual(mentor_timeline[0]["actor"], self.applicant.profile.display_name)
        self.assertEqual(mentor_timeline[1]["actor"], self.finance.profile.display_name)
