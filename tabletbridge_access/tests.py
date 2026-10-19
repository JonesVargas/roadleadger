from datetime import timedelta
from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient
from .models import AccessGrant, DeviceSession
from .service import digest


@override_settings(SECURE_SSL_REDIRECT=False, PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class AuthTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user('bridge@example.test', 'test-only-password', full_name='Jones')
        self.grant = AccessGrant.objects.create(user=self.user, approved=True)
        self.client = APIClient()

    def post(self, route, data):
        return self.client.post('/api/v1/tabletbridge/' + route + '/', data, format='json', secure=True)

    def login(self):
        return self.post('login', {'email': self.user.email, 'password': 'test-only-password', 'platform': 'android'})

    def me(self, token):
        return self.client.get('/api/v1/tabletbridge/me/', secure=True, HTTP_AUTHORIZATION='Bearer ' + token)

    def test_login_profile_no_finance_or_farm_binding(self):
        response = self.login()
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['user']['id'], self.user.pk)
        self.assertFalse(data['commerce_enabled'])
        self.assertIsNone(data['farm_link'])
        session = DeviceSession.objects.get()
        self.assertEqual(session.access_hash, digest(data['access_token']))
        self.assertNotIn(data['refresh_token'], str(session.__dict__))
        self.assertEqual(self.me(data['access_token']).status_code, 200)

    def test_wrong_password_and_inactive(self):
        self.assertEqual(self.post('login', {'email': self.user.email, 'password': 'wrong'}).json()['code'], 'invalid_credentials')
        self.user.is_active = False
        self.user.save()
        self.assertEqual(self.login().json()['code'], 'account_inactive')
        self.assertEqual(DeviceSession.objects.count(), 0)

    def test_specific_grant_not_ets_lifetime_or_subscription(self):
        self.grant.delete()
        self.user.lifetime_access = True
        self.user.manual_plan = 'company'
        self.user.save()
        self.assertEqual(self.login().json()['code'], 'product_not_authorized')

    def test_unreleased_expired_and_revoked(self):
        self.grant.approved = False
        self.grant.save()
        self.assertEqual(self.login().json()['code'], 'access_not_released')
        self.grant.approved = True
        self.grant.expires_at = timezone.now() - timedelta(seconds=1)
        self.grant.save()
        self.assertEqual(self.login().json()['code'], 'access_expired')
        self.grant.expires_at = None
        self.grant.save()
        tokens = self.login().json()
        self.grant.blocked = True
        self.grant.save()
        self.assertEqual(self.me(tokens['access_token']).json()['code'], 'access_revoked')
        self.assertEqual(self.post('refresh', {'refresh_token': tokens['refresh_token']}).status_code, 403)
        self.assertEqual(self.post('logout', {'refresh_token': tokens['refresh_token']}).status_code, 200)

    def test_rotation_expiry_logout_and_device_independence(self):
        first = self.login().json()
        second = self.login().json()
        renewed = self.post('refresh', {'refresh_token': first['refresh_token']})
        self.assertEqual(renewed.status_code, 200)
        self.assertEqual(self.me(first['access_token']).status_code, 401)
        self.assertEqual(self.post('refresh', {'refresh_token': first['refresh_token']}).status_code, 401)
        new = renewed.json()
        self.assertEqual(self.post('logout', {'refresh_token': new['refresh_token']}).status_code, 200)
        self.assertEqual(self.post('refresh', {'refresh_token': new['refresh_token']}).status_code, 401)
        self.assertEqual(self.me(second['access_token']).status_code, 200)
        DeviceSession.objects.filter(access_hash=digest(second['access_token'])).update(refresh_expires_at=timezone.now())
        self.assertEqual(self.post('refresh', {'refresh_token': second['refresh_token']}).status_code, 401)

    def test_isolation_protection_and_password_change(self):
        tokens = self.login().json()
        other = get_user_model().objects.create_user('other@example.test', 'test-only-password', full_name='Other')
        AccessGrant.objects.create(user=other, approved=True)
        self.assertEqual(self.me(tokens['access_token']).json()['user']['id'], self.user.pk)
        self.assertEqual(self.me('invalid').status_code, 401)
        self.user.set_password('changed-only-for-test')
        self.user.save()
        self.assertEqual(self.me(tokens['access_token']).status_code, 401)

    def test_throttling_and_https(self):
        self.assertEqual(self.client.post('/api/v1/tabletbridge/login/', {}, format='json').status_code, 400)
        cache.clear()
        for _ in range(5):
            self.post('login', {'email': 'missing@example.test', 'password': 'bad'})
        self.assertEqual(self.login().status_code, 429)

    def test_admin_is_not_available_to_normal_users_and_no_secrets_in_logs(self):
        self.client.force_login(self.user)
        response=self.client.get('/admin/tabletbridge_access/accessgrant/', secure=True)
        self.assertEqual(response.status_code,302)
        tokens=self.login().json()
        with self.assertLogs('django.request',level='WARNING') as recorded:
            self.me('invalid-secret-test-token')
        logs='\n'.join(recorded.output)
        self.assertNotIn('invalid-secret-test-token',logs)
        self.assertNotIn(tokens['access_token'],logs)
        self.assertNotIn('test-only-password',logs)
