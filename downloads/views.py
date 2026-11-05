from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, render
from django_ratelimit.decorators import ratelimit

from .models import AppVersion, DownloadEvent
from subscriptions.access import can_download, allowed_apps
from tabletbridge_access.service import decision
from .access import application_access, visible_versions


@login_required
def index(request):
    if not settings.MANUAL_APP_ACCESS and not allowed_apps(request.user) and decision(request.user)[0]!='authorized':
        return HttpResponseForbidden("Uma assinatura ativa ou acesso vitalício é necessário.")
    return render(request, "downloads/index.html", {"versions": visible_versions(request.user), "app_access": application_access(request.user) if settings.MANUAL_APP_ACCESS else []})


@login_required
@ratelimit(key="user", rate="10/h", block=True)
def download(request, pk):
    version = get_object_or_404(AppVersion, pk=pk, published=True)
    allowed = can_download(request.user, version)
    DownloadEvent.objects.create(
        user=request.user,
        version=version,
        ip=request.META.get("REMOTE_ADDR"),
        user_agent=request.META.get("HTTP_USER_AGENT", ""),
        allowed=allowed,
    )
    if not allowed:
        return HttpResponseForbidden("Seu acesso a este aplicativo não está liberado ou expirou.")
    try:
        file = version.file.open("rb")
    except FileNotFoundError as exc:
        raise Http404("Arquivo da versão indisponível.") from exc
    response = FileResponse(file, as_attachment=True, filename=version.file.name.rsplit("/", 1)[-1])
    response["Cache-Control"] = "private, no-store"
    return response
