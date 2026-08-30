from django.contrib.auth.decorators import login_required
from django.http import FileResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, render
from django_ratelimit.decorators import ratelimit

from .models import AppVersion, DownloadEvent


@login_required
def index(request):
    sub = request.user.subscriptions.filter(status__in=["active", "authorized"]).first()
    if not request.user.lifetime_access and not sub:
        return HttpResponseForbidden("Uma assinatura ativa ou acesso vitalício é necessário.")
    return render(request, "downloads/index.html", {"versions": AppVersion.objects.filter(published=True)})


@login_required
@ratelimit(key="user", rate="10/h", block=True)
def download(request, pk):
    version = get_object_or_404(AppVersion, pk=pk, published=True)
    sub = (
        request.user.subscriptions.select_related("plan").filter(status__in=["active", "authorized"]).first()
    )
    allowed = request.user.lifetime_access or bool(
        sub and (not version.min_plan_codes or sub.plan.code in version.min_plan_codes)
    )
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
