from django.contrib.auth.decorators import login_required
from django.http import FileResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, render
from django_ratelimit.decorators import ratelimit

from .models import AppVersion, DownloadEvent
from subscriptions.access import can_download, allowed_apps


@login_required
def index(request):
    if not allowed_apps(request.user):
        return HttpResponseForbidden("Uma assinatura ativa ou acesso vitalício é necessário.")
    return render(request, "downloads/index.html", {"versions": [v for v in AppVersion.objects.filter(published=True) if can_download(request.user, v)]})


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
        return HttpResponseForbidden("Uma assinatura ativa compatível é necessária.")
    return FileResponse(
        version.file.open("rb"), as_attachment=True, filename=version.file.name.rsplit("/", 1)[-1]
    )
