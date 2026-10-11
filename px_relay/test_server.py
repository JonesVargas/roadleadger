import asyncio
import unittest

from websockets.asyncio.client import connect
from websockets.asyncio.server import serve
from websockets.exceptions import InvalidStatus

from px_relay.server import AudioRelay, Authorization, ChannelAuthorization


class RelayTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        users = {"a": Authorization(1, 2, "call-1"),
                 "b": Authorization(2, 1, "call-1")}

        def authorize(token, call_id):
            if token not in users or users[token].call_id != call_id:
                raise ValueError("Chamada não autorizada")
            return users[token]

        channels = {"a": ChannelAuthorization(1, "public:19", "ALFA"),
                    "b": ChannelAuthorization(2, "public:19", "BRAVO"),
                    "c": ChannelAuthorization(3, "public:19", "CHARLIE")}

        def authorize_channel(token, channel):
            if token not in channels or channels[token].channel != channel:
                raise ValueError("Canal não autorizado")
            return channels[token]

        self.relay = AudioRelay(authorize, authorize_channel)
        self.server = await serve(self.relay.handle, "127.0.0.1", 0,
                                  process_request=self.relay.process_request)
        self.url = f"ws://127.0.0.1:{self.server.sockets[0].getsockname()[1]}/px"

    async def asyncTearDown(self):
        self.server.close()
        await self.server.wait_closed()

    async def test_requires_site_authorized_accepted_call(self):
        with self.assertRaises(InvalidStatus):
            async with connect(self.url, additional_headers={
                    "Authorization": "Bearer bad", "X-RoadLedger-Call": "call-1"}):
                pass

    async def test_relay_sends_only_between_call_participants(self):
        headers_a = {"Authorization": "Bearer a", "X-RoadLedger-Call": "call-1"}
        headers_b = {"Authorization": "Bearer b", "X-RoadLedger-Call": "call-1"}
        async with connect(self.url, additional_headers=headers_a) as alice:
            async with connect(self.url, additional_headers=headers_b) as bob:
                await alice.send(b"a" * 640)
                self.assertEqual(await asyncio.wait_for(bob.recv(), 2),
                                 b"a" * 640)
                await bob.send(b"b" * 640)
                self.assertEqual(await asyncio.wait_for(alice.recv(), 2), b"b" * 640)
        for _ in range(10):
            if not self.relay.rooms:
                break
            await asyncio.sleep(0.01)
        self.assertFalse(self.relay.rooms)

    async def test_channel_allows_one_speaker_at_a_time(self):
        import json
        headers = lambda token: {"Authorization": "Bearer " + token,
                                 "X-RoadLedger-Channel": "public:19"}
        async with connect(self.url, additional_headers=headers("a")) as alice:
            async with connect(self.url, additional_headers=headers("b")) as bob:
                await alice.recv()
                await bob.recv()
                await alice.send(b"a" * 640)
                state = json.loads(await bob.recv())
                self.assertEqual(state, {"type": "speaking", "user_id": 1,
                                         "callsign": "ALFA"})
                self.assertEqual(json.loads(await alice.recv()), state)
                self.assertEqual(await bob.recv(), b"a" * 640)
                await bob.send(b"b" * 640)
                with self.assertRaises(TimeoutError):
                    await asyncio.wait_for(alice.recv(), 0.1)
                await alice.send("release")
                self.assertEqual(json.loads(await bob.recv())["user_id"], None)
                self.assertEqual(json.loads(await alice.recv())["user_id"], None)
                await bob.send(b"b" * 640)
                self.assertEqual(json.loads(await alice.recv())["user_id"], 2)
                self.assertEqual(await alice.recv(), b"b" * 640)


if __name__ == "__main__":
    unittest.main()
