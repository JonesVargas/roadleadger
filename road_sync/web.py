import json

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import render
from django.views.decorators.http import require_GET

from .service import feed


@login_required
@require_GET
def center(request):
    return render(request, "road_sync/center.html")


@login_required
@require_GET
def stream(request):
    # Bounded SSE response: reconnect resumes with Last-Event-ID; no worker sleeps.
    try:
        cursor = int(request.headers.get("Last-Event-ID") or request.GET.get("cursor", 0))
        if cursor < 0:
            raise ValueError()
    except (TypeError, ValueError):
        return HttpResponseBadRequest("Cursor inválido.")
    batch = feed(request.user, cursor)
    chunks = ["retry: 15000\n\n"]
    for event in batch["events"]:
        chunks.append("id: " + str(event["cursor"]) + "\ndata: " + json.dumps(event) + "\n\n")
    if not batch["events"]:
        chunks.append(": aguardando\n\n")
    response = HttpResponse("".join(chunks), content_type="text/event-stream")
    response["Cache-Control"] = "no-store"
    response["X-Accel-Buffering"] = "no"
    return response
