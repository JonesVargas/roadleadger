# RoadLedger PX relay

This is a separate service from the RoadLedger site. It accepts secure WebSocket
connections at `/px` and has a `/health` endpoint. It forwards 16 kHz mono
16-bit PCM frames between participants only after the site confirms an accepted
private call or access to a public/company channel. The relay does not save
audio. It checks access again every 10 seconds.

Deploy one replica using this directory as the Docker build root. Set:

- `ROADLEDGER_SITE_URL`: HTTPS origin of the RoadLedger site.
- `PORT`: supplied by the host.

Set `ROADLEDGER_PX_URL=wss://<relay-domain>/px` on the **site** service. The
desktop app reads that address from the authenticated `/api/v1/radio/config/`
endpoint. Do not put a bearer token in the relay URL or logs.

The channel speaker lease is held in process memory. Multiple replicas would
split listeners, so a multi-replica deployment needs shared room coordination.
Audio uses uncompressed PCM (about 32 kB/s per active speaker before network
overhead); monitor bandwidth and costs before opening public channels widely.

Local tests: `python -m unittest px_relay.test_server` from the Connect project
root. End-to-end validation needs two player accounts on separate PCs and a
deployed WSS relay. The site must be migrated before the app can use the radio.
