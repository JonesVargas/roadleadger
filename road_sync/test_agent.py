import uuid

from django.test import TestCase, override_settings

from accounts.models import User
from licenses.models import ApiToken

from .models import AgentProbe, GameProfileBinding


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class AgentProbeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("probe@example.com", "test", lifetime_access=True)
        self.other = User.objects.create_user("probe-other@example.com", "test", lifetime_access=True)
        self.tokens = {u.pk: ApiToken.issue(u)[1] for u in (self.user, self.other)}
        self.installation = str(uuid.uuid4())

    def call(self, user, path, data=None):
        method = self.client.get if data is None else self.client.post
        return method(
            "/api/v1/sync/" + path,
            data=data,
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer " + self.tokens[user.pk],
        )

    def test_binding_and_probe_are_idempotent_and_private(self):
        values = {"installation_id": self.installation, "game": "ATS", "profile_key": "a" * 64}
        result = self.call(self.user, "profiles/", values)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(self.call(self.user, "profiles/", values).json(), result.json())
        self.assertEqual(GameProfileBinding.objects.count(), 1)
        request = {"binding_id": result.json()["binding_id"], "idempotency_key": str(uuid.uuid4())}
        probe = self.call(self.user, "probe/", request).json()
        self.assertEqual(self.call(self.user, "probe/", request).json(), probe)
        self.assertEqual(AgentProbe.objects.count(), 1)
        self.assertEqual(self.call(self.other, "probe/", request).status_code, 404)
        path = "commands/?installation_id=" + self.installation
        command = self.call(self.user, path).json()[0]
        self.assertEqual(self.call(self.other, path).json(), [])
        response = {"installation_id": self.installation, "challenge": command["challenge"]}
        self.assertEqual(
            self.call(self.other, "commands/" + command["id"] + "/ack/", response).status_code, 404
        )
        good = self.call(self.user, "commands/" + command["id"] + "/ack/", response)
        self.assertEqual(good.json()["game_changed"], False)
        self.assertEqual(
            self.call(self.user, "commands/" + command["id"] + "/ack/", response).json(), good.json()
        )
        self.assertEqual(self.call(self.user, path).json(), [])

    def test_no_plan_cannot_bind(self):
        self.user.lifetime_access = False
        self.user.save()
        self.assertEqual(
            self.call(
                self.user,
                "profiles/",
                {"installation_id": self.installation, "game": "ETS2", "profile_key": "a" * 64},
            ).status_code,
            403,
        )
