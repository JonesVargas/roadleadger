"""Small private-call audio relay; RoadLedger site remains the authority."""

import asyncio
import json
import os
from dataclasses import dataclass
from http import HTTPStatus
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from websockets.asyncio.server import serve

PCM_FRAME_BYTES = 640

@dataclass(frozen=True)
class Authorization:
    user_id: int
    peer_id: int
    call_id: str


@dataclass(frozen=True)
class ChannelAuthorization:
    user_id: int
    channel: str
    callsign: str


def _site_json(path, token):
    site = os.environ["ROADLEDGER_SITE_URL"].rstrip("/")
    if not site.startswith("https://") and not site.startswith("http://127.0.0.1:"):
        raise ValueError("O site de autenticação deve usar HTTPS.")
    request = Request(site + path, headers={"Authorization": "Bearer " + token,
                                            "Accept": "application/json"})
    with urlopen(request, timeout=6) as response:
        return json.load(response)


def authorize(token, call_id):
    """Do not trust call membership supplied by the desktop client."""
    if not token or not call_id:
        raise ValueError("Credenciais ausentes.")
    me = _site_json("/api/v1/me/", token)
    calls = _site_json("/api/v1/radio/calls/", token)
    call = next((item for item in calls if item["id"] == call_id and
                 item["status"] == "accepted"), None)
    if call is None:
        raise ValueError("Chamada não autorizada ou encerrada.")
    return Authorization(int(me["id"]), int(call["peer"]["user_id"]), call_id)


def authorize_channel(token, channel):
    if not token or not channel:
        raise ValueError("Credenciais ausentes.")
    details = _site_json("/api/v1/radio/channel-access/?" +
                         urlencode({"channel": channel}), token)
    if details.get("channel") != channel:
        raise ValueError("Canal não autorizado.")
    return ChannelAuthorization(int(details["user_id"]), channel,
                                str(details["callsign"]))


class AudioRelay:
    def __init__(self, authorizer=authorize, channel_authorizer=authorize_channel):
        self.authorizer = authorizer
        self.channel_authorizer = channel_authorizer
        self.rooms = {}
        self.channels = {}

    async def process_request(self, connection, request):
        if request.path == "/health":
            return connection.respond(HTTPStatus.OK, "ok\n")
        if request.path != "/px":
            return connection.respond(HTTPStatus.NOT_FOUND, "Not found\n")
        header = request.headers.get("Authorization", "")
        token = header[7:] if header.startswith("Bearer ") else ""
        call_id = request.headers.get("X-RoadLedger-Call", "")
        channel = request.headers.get("X-RoadLedger-Channel", "")
        if bool(call_id) == bool(channel):
            return connection.respond(HTTPStatus.BAD_REQUEST, "Escolha chamada ou canal\n")
        try:
            connection.authorization = await asyncio.to_thread(
                self.channel_authorizer if channel else self.authorizer,
                token, channel or call_id)
        except (OSError, ValueError, KeyError, TypeError):
            return connection.respond(HTTPStatus.UNAUTHORIZED, "Unauthorized\n")
        return None

    async def _watch(self, connection, authorization):
        while True:
            await asyncio.sleep(10)
            header = connection.request.headers.get("Authorization", "")
            token = header[7:] if header.startswith("Bearer ") else ""
            try:
                current = await asyncio.to_thread(
                    self.channel_authorizer if isinstance(authorization, ChannelAuthorization)
                    else self.authorizer, token,
                    authorization.channel if isinstance(authorization, ChannelAuthorization)
                    else authorization.call_id)
            except (OSError, ValueError, KeyError, TypeError):
                await connection.close(code=4003, reason="Chamada encerrada")
                return
            if current != authorization:
                await connection.close(code=4003, reason="Permissão alterada")
                return

    async def handle(self, connection):
        identity = connection.authorization
        if isinstance(identity, ChannelAuthorization):
            await self._handle_channel(connection, identity)
            return
        frame_window = asyncio.get_running_loop().time()
        frame_count = 0
        room = self.rooms.setdefault(identity.call_id, {})
        if any(peer_id not in (identity.user_id, identity.peer_id) for peer_id in room):
            await connection.close(code=4003, reason="Participante inválido")
            return
        prior = room.get(identity.user_id)
        if prior is not None:
            await prior.close(code=4001, reason="Nova conexão")
        room[identity.user_id] = connection
        watcher = asyncio.create_task(self._watch(connection, identity))
        try:
            async for frame in connection:
                if not isinstance(frame, bytes) or len(frame) != PCM_FRAME_BYTES:
                    await connection.close(code=1003, reason="Quadro de áudio inválido")
                    break
                now = asyncio.get_running_loop().time()
                if now - frame_window >= 1:
                    frame_window, frame_count = now, 0
                frame_count += 1
                if frame_count > 75:
                    await connection.close(code=4008, reason="Áudio excessivo")
                    break
                peer = room.get(identity.peer_id)
                if peer is not None:
                    try:
                        await peer.send(frame)
                    except Exception:
                        pass
        finally:
            watcher.cancel()
            if room.get(identity.user_id) is connection:
                room.pop(identity.user_id)
            if not room:
                self.rooms.pop(identity.call_id, None)

    async def _broadcast_channel(self, room, text):
        for member in list(room["members"].values()):
            try:
                await member.send(text)
            except Exception:
                pass

    async def _handle_channel(self, connection, identity):
        frame_window = asyncio.get_running_loop().time()
        frame_count = 0
        room = self.channels.setdefault(identity.channel, {
            "members": {}, "speaker": None, "speaker_name": None,
            "last_audio": 0.0})
        prior = room["members"].get(identity.user_id)
        if prior is not None:
            await prior.close(code=4001, reason="Nova conexão")
        room["members"][identity.user_id] = connection
        watcher = asyncio.create_task(self._watch(connection, identity))
        try:
            await connection.send(json.dumps({"type": "speaking",
                                              "user_id": room["speaker"],
                                              "callsign": room["speaker_name"]}))
            async for frame in connection:
                if isinstance(frame, str):
                    if frame == "release" and room["speaker"] == identity.user_id:
                        room["speaker"] = None
                        room["speaker_name"] = None
                        await self._broadcast_channel(room,
                            json.dumps({"type": "speaking", "user_id": None,
                                        "callsign": None}))
                    continue
                if len(frame) != PCM_FRAME_BYTES:
                    await connection.close(code=1003, reason="Quadro de áudio inválido")
                    break
                now = asyncio.get_running_loop().time()
                if now - frame_window >= 1:
                    frame_window, frame_count = now, 0
                frame_count += 1
                if frame_count > 75:
                    await connection.close(code=4008, reason="Áudio excessivo")
                    break
                if room["speaker"] is not None and now - room["last_audio"] > 0.8:
                    room["speaker"] = None
                    room["speaker_name"] = None
                if room["speaker"] is None:
                    room["speaker"] = identity.user_id
                    room["speaker_name"] = identity.callsign
                    await self._broadcast_channel(room,
                        json.dumps({"type": "speaking", "user_id": identity.user_id,
                                    "callsign": identity.callsign}))
                if room["speaker"] != identity.user_id:
                    continue
                room["last_audio"] = now
                for user_id, member in list(room["members"].items()):
                    if user_id != identity.user_id:
                        try:
                            await member.send(frame)
                        except Exception:
                            pass
        finally:
            watcher.cancel()
            if room["members"].get(identity.user_id) is connection:
                room["members"].pop(identity.user_id)
            if room["speaker"] == identity.user_id:
                room["speaker"] = None
                room["speaker_name"] = None
                await self._broadcast_channel(room,
                    json.dumps({"type": "speaking", "user_id": None,
                                "callsign": None}))
            if not room["members"]:
                self.channels.pop(identity.channel, None)


async def main():
    relay = AudioRelay()
    port = int(os.environ.get("PORT", "8765"))
    async with serve(relay.handle, "0.0.0.0", port,
                     process_request=relay.process_request,
                     max_size=4096, compression=None):
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
