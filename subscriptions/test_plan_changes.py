from datetime import timedelta
from decimal import Decimal
from unittest.mock import Mock, patch
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from accounts.models import User
from payments.services import apply_provider_payment, apply_provider_subscription
from payments.models import Payment
from .models import Plan, Subscription, PlanChange
from .plan_changes import quote, request_change, finish, renew_pix

@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class PlanChangeTests(TestCase):
    def setUp(self):
        self.now=timezone.now()
        clock=patch("subscriptions.plan_changes.timezone.now",return_value=self.now)
        clock.start();self.addCleanup(clock.stop)
        self.user=User.objects.create_user("change@test.test","password")
        self.old=Plan.objects.create(code="change-player",name="Player",price=Decimal("5.99"),interval="month")
        self.new=Plan.objects.create(code="change-company",name="Empresa",product="company",price=Decimal("14.99"),interval="month")
        self.sub=Subscription.objects.create(user=self.user,plan=self.old,status="active",provider="mercado_pago",provider_subscription_id="pre-1",current_period_start=self.now-timedelta(days=15),current_period_end=self.now+timedelta(days=15))
        self.gateway=Mock()
        self.gateway.create_plan_change_preference.return_value={"init_point":"https://www.mercadopago.com.br/test"}

    def request(self,target=None,amount="4.50"):
        return request_change(self.user,(target or self.new).pk,self.gateway,expected_amount=amount)

    def payload(self,change,id="pay-1",amount=None):
        return {"id":id,"status":"approved","currency_id":"BRL","transaction_amount":str(change.amount_due if amount is None else amount),"date_approved":self.now.isoformat(),"metadata":{"plan_change_id":str(change.pk),"subscription_id":self.sub.pk}}

    def test_upgrade_waits_for_payment_and_is_idempotent(self):
        change=self.request()
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.plan_id,self.old.pk)
        self.assertEqual(change.amount_due,Decimal("4.50"))
        self.assertEqual(self.request().pk,change.pk)
        self.gateway.create_plan_change_preference.assert_called_once()
        apply_provider_payment(self.payload(change),client=self.gateway)
        apply_provider_payment(self.payload(change),client=self.gateway)
        self.sub.refresh_from_db();change.refresh_from_db()
        self.assertEqual(self.sub.plan_id,self.new.pk)
        self.assertEqual(change.status,"applied")
        self.assertEqual(self.sub.renewal_amount,Decimal("14.99"))
        self.gateway.update_subscription_amount.assert_called_once()
        self.assertEqual(Payment.objects.count(),1)

    def test_downgrade_immediate_credit_reduces_next_charge(self):
        self.sub.plan=self.new;self.sub.save()
        change=self.request(self.old,"0.00")
        self.sub.refresh_from_db()
        self.assertEqual(change.status,"applied")
        self.assertEqual(self.sub.plan_id,self.old.pk)
        self.assertEqual(self.sub.credit_balance,Decimal("4.50"))
        self.assertEqual(self.sub.renewal_amount,Decimal("1.49"))
        self.gateway.create_plan_change_preference.assert_not_called()

    def test_recurring_renewal_consumes_credit_once_and_restores_full_price(self):
        self.sub.plan=self.new;self.sub.save();self.request(self.old,"0")
        self.sub.refresh_from_db();boundary=self.sub.current_period_end
        payload={"id":"renew-1","status":"approved","currency_id":"BRL","transaction_amount":"1.49","date_approved":boundary.isoformat(),"metadata":{"preapproval_id":"pre-1"}}
        apply_provider_payment(payload,client=self.gateway)
        self.sub.refresh_from_db();end=self.sub.current_period_end
        apply_provider_payment(payload,client=self.gateway)
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.credit_balance,0)
        self.assertEqual(self.sub.renewal_amount,Decimal("5.99"))
        self.assertEqual(self.sub.current_period_end,end)
        self.assertGreater(end,boundary)

    def test_credit_covering_whole_cycle_prepays_and_delays_next_charge(self):
        self.sub.plan=self.new;self.sub.current_period_start=self.now;self.sub.current_period_end=self.now+timedelta(days=30);self.sub.save()
        end=self.sub.current_period_end
        self.request(self.old,"0")
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.credit_balance,Decimal("3.01"))
        self.assertEqual(self.sub.renewal_amount,Decimal("2.98"))
        self.assertGreater(self.sub.current_period_end,end)
        self.assertEqual(len(self.sub.billing_coverage),2)

    def test_failed_gateway_update_can_retry_without_charging_twice(self):
        change=self.request()
        self.gateway.update_subscription_amount.side_effect=RuntimeError("offline")
        apply_provider_payment(self.payload(change),client=self.gateway)
        change.refresh_from_db();self.sub.refresh_from_db()
        self.assertEqual(change.status,"paid")
        self.assertEqual(self.sub.plan_id,self.old.pk)
        self.gateway.update_subscription_amount.side_effect=None
        finish(change.pk,self.gateway)
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.plan_id,self.new.pk)
        self.assertEqual(Payment.objects.count(),1)

    def test_invalid_amount_or_currency_does_not_unlock(self):
        change=self.request()
        apply_provider_payment(self.payload(change,amount="0.01"),client=self.gateway)
        payload=self.payload(change,id="wrong-currency");payload["currency_id"]="USD"
        apply_provider_payment(payload,client=self.gateway)
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.plan_id,self.old.pk)
        self.gateway.update_subscription_amount.assert_not_called()

    def test_only_owner_can_change_and_confirmation_is_required(self):
        self.client.force_login(self.user)
        page=self.client.get(reverse("subscriptions:change_plan"))
        self.assertContains(page,"Trocar de plano")
        self.assertContains(page,"4,50")
        self.client.post(reverse("subscriptions:change_plan"),{"action":"change","target":self.new.pk,"amount":"4.50"})
        self.assertFalse(PlanChange.objects.exists())
        with self.assertRaises(ValueError):self.request(amount="0.01")
        other=User.objects.create_user("other-change@test.test","password")
        with self.assertRaises(ValueError):request_change(other,self.new.pk,self.gateway,expected_amount="4.50")

    def test_quotes_reject_expired_and_different_intervals(self):
        with self.assertRaises(ValueError):quote(self.sub,self.new,self.sub.current_period_end)
        self.new.interval="year"
        with self.assertRaises(ValueError):quote(self.sub,self.new,self.now)

    def test_provider_status_update_preserves_prepaid_coverage(self):
        self.sub.plan=self.new;self.sub.current_period_start=self.now;self.sub.current_period_end=self.now+timedelta(days=30);self.sub.save()
        self.request(self.old,"0");self.sub.refresh_from_db();end=self.sub.current_period_end
        apply_provider_subscription({"id":"pre-1","external_reference":str(self.sub.pk),"status":"authorized","date_created":(self.now-timedelta(days=100)).isoformat(),"next_payment_date":(self.now+timedelta(days=1)).isoformat()})
        self.sub.refresh_from_db();self.assertEqual(self.sub.current_period_end,end)

    def test_pix_renewal_uses_credit_and_does_not_update_card(self):
        self.sub.provider="mercado_pago_pix";self.sub.current_period_end=self.now-timedelta(seconds=1);self.sub.credit_balance=Decimal("2.00");self.sub.save()
        change=renew_pix(self.user,self.gateway)
        self.assertEqual(change.amount_due,Decimal("3.99"))
        apply_provider_payment(self.payload(change),client=self.gateway)
        self.sub.refresh_from_db()
        self.assertTrue(self.sub.grants_access)
        self.assertEqual(self.sub.credit_balance,0)
        self.gateway.update_subscription_amount.assert_not_called()

    def test_duplicate_second_payment_is_credited_once(self):
        change=self.request()
        apply_provider_payment(self.payload(change),client=self.gateway)
        second=self.payload(change,id="second-payment")
        second["status"]="pending"
        apply_provider_payment(second,client=self.gateway)
        second["status"]="approved"
        apply_provider_payment(second,client=self.gateway)
        apply_provider_payment(second,client=self.gateway)
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.credit_balance,Decimal("4.50"))

    def test_older_pending_notification_does_not_reapply_renewal(self):
        self.sub.plan=self.new;self.sub.save();self.request(self.old,"0")
        self.sub.refresh_from_db()
        payload={"id":"renew-out-of-order","status":"approved","currency_id":"BRL","transaction_amount":"1.49","date_approved":self.sub.current_period_end.isoformat(),"metadata":{"preapproval_id":"pre-1"}}
        apply_provider_payment(payload,client=self.gateway)
        self.sub.refresh_from_db();end=self.sub.current_period_end
        payload["status"]="pending";apply_provider_payment(payload,client=self.gateway)
        payload["status"]="approved";apply_provider_payment(payload,client=self.gateway)
        self.sub.refresh_from_db();self.assertEqual(self.sub.current_period_end,end)

    def test_authorized_invoice_fetches_underlying_payment(self):
        from payments.models import WebhookEvent
        from payments.services import process_webhook
        self.sub.plan=self.new;self.sub.save();self.request(self.old,"0")
        self.sub.refresh_from_db()
        self.gateway.get_authorized_payment.return_value={"preapproval_id":"pre-1","payment":{"id":"invoice-payment"}}
        self.gateway.get_payment.return_value={"id":"invoice-payment","status":"approved","currency_id":"BRL","transaction_amount":"1.49","date_approved":self.sub.current_period_end.isoformat()}
        event=WebhookEvent.objects.create(event_key="authorized-1",topic="subscription_authorized_payment",resource_id="invoice-1",signature_valid=True,payload={})
        process_webhook(event,self.gateway)
        self.gateway.get_authorized_payment.assert_called_once_with("invoice-1")
        self.gateway.get_payment.assert_called_once_with("invoice-payment")
        self.sub.refresh_from_db();self.assertEqual(self.sub.credit_balance,0)

    @patch("payments.services.requests.put")
    @patch("payments.services.get_mercado_pago_credentials")
    def test_provider_update_uses_documented_amount_and_date(self,credentials,put):
        from payments.services import MercadoPagoClient
        credentials.return_value.access_token="test-only-token"
        MercadoPagoClient().update_subscription_amount("pre-1",self.new,Decimal("14.99"),self.sub.current_period_end)
        payload=put.call_args.kwargs["json"]
        self.assertEqual(payload["auto_recurring"],{"transaction_amount":14.99,"currency_id":"BRL"})
        self.assertEqual(payload["next_payment_date"],self.sub.current_period_end.isoformat())
