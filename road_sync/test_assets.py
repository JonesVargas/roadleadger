import uuid
from decimal import Decimal
from unittest.mock import patch
from django.test import TestCase, override_settings
from rest_framework.exceptions import ValidationError, PermissionDenied
from accounts.models import User
from .assets import purchase, confirm_purchase, bank_for
from .models import VirtualAccount, VirtualAsset, VirtualLoan
from .ledger import balance, post


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class AssetTests(TestCase):
    def setUp(self):
        self.user=User.objects.create_user("asset@example.com","test")
        self.other=User.objects.create_user("asset-other@example.com","test")
        self.account=VirtualAccount.objects.create(owner=self.user,game="ATS",label="Player",reconciled=True)
        bank=bank_for(self.account)
        post("opening-asset-test","Fixture",{self.account.pk:50000,bank.pk:-50000})
        self.values=dict(vehicle_type="truck",brand="Volvo",model="VNL",condition="used",
                         odometer_km=Decimal("200000.000"),price=Decimal("100000"),
                         down_payment=Decimal("50000"),term_days=24)

    def test_financing_credits_only_financed_amount_and_confirmation_is_once(self):
        key=uuid.uuid4()
        asset=purchase(self.user,self.account.pk,key,self.values)
        self.assertEqual(balance(self.account),100000)
        self.assertEqual(asset.status,"pending_game_purchase")
        self.assertEqual(purchase(self.user,self.account.pk,key,self.values).pk,asset.pk)
        self.assertEqual(VirtualLoan.objects.count(),1)
        confirm_purchase(self.user,asset.pk)
        confirm_purchase(self.user,asset.pk)
        self.assertEqual(balance(self.account),0)
        asset.refresh_from_db()
        self.assertEqual(asset.status,"active")
        self.assertEqual(asset.odometer_km,200000)

    def test_other_account_and_used_trailer_are_rejected(self):
        with self.assertRaises(PermissionDenied):
            purchase(self.other,self.account.pk,uuid.uuid4(),self.values)
        with self.assertRaises(ValidationError):
            purchase(self.user,self.account.pk,uuid.uuid4(),dict(self.values,vehicle_type="trailer"))
        self.assertEqual(balance(self.account),50000)

    def test_atomic_rollback(self):
        with patch("road_sync.assets.notify",side_effect=RuntimeError("test")):
            with self.assertRaises(RuntimeError):
                purchase(self.user,self.account.pk,uuid.uuid4(),self.values)
        self.assertEqual(balance(self.account),50000)
        self.assertEqual(VirtualAsset.objects.count(),0)
        self.assertEqual(VirtualLoan.objects.count(),0)
