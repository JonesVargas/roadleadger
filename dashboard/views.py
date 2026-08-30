from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from audit.models import AuditEvent
from core.models import FAQ, Feature, LegalPage, ServiceStatus, SocialLink, UpdatePost
from downloads.models import AppVersion, DownloadEvent
from payments.models import Payment
from subscriptions.models import Plan, Subscription

from .forms import AppVersionForm, FAQForm, FeatureForm, LegalPageForm, PlanForm, ServiceStatusForm, SocialLinkForm, UpdatePostForm


@login_required
def home(request):
    if request.user.is_superuser:
        return redirect("dashboard:manager")
    sub = request.user.subscriptions.select_related("plan").order_by("-created_at").first()
    return render(request, "dashboard/home.html", {"subscription": sub, "devices": request.user.devices.filter(revoked_at__isnull=True), "versions": AppVersion.objects.filter(published=True)[:3], "payments": Payment.objects.filter(subscription__user=request.user)[:10]})


def superuser_required(view):
    return user_passes_test(lambda user: user.is_authenticated and user.is_superuser)(view)


MANAGED = {
    "version": (AppVersion, AppVersionForm, "versoes"),
    "plan": (Plan, PlanForm, "planos"),
    "feature": (Feature, FeatureForm, "conteudo"),
    "faq": (FAQ, FAQForm, "conteudo"),
    "update": (UpdatePost, UpdatePostForm, "conteudo"),
    "status": (ServiceStatus, ServiceStatusForm, "conteudo"),
    "social": (SocialLink, SocialLinkForm, "conteudo"),
    "legal": (LegalPage, LegalPageForm, "conteudo"),
}


def _manager_url(section="visao-geral"):
    return f'{reverse("dashboard:manager")}?section={section}'


@superuser_required
def manager(request):
    entity, edit_id = request.GET.get("edit"), request.GET.get("id")
    edit_object = get_object_or_404(MANAGED[entity][0], pk=edit_id) if entity in MANAGED and edit_id else None
    forms = {key: form_class(instance=edit_object if entity == key else None, prefix=key) for key, (_model, form_class, _section) in MANAGED.items()}
    context = {
        "users": User.objects.count(),
        "active_subscriptions": Subscription.objects.filter(status__in=["active", "authorized"]).count(),
        "lifetime_users": User.objects.filter(lifetime_access=True).count(),
        "downloads": DownloadEvent.objects.count(),
        "revenue": Payment.objects.filter(status__in=["approved", "authorized", "paid"]).aggregate(total=Sum("amount"))["total"] or 0,
        "recent_audit": AuditEvent.objects.select_related("actor")[:12],
        "versions": AppVersion.objects.all(), "plans": Plan.objects.all(), "features": Feature.objects.all(),
        "faqs": FAQ.objects.all(), "updates": UpdatePost.objects.all(), "services": ServiceStatus.objects.all(),
        "social_links": SocialLink.objects.all(), "legal_pages": LegalPage.objects.all(),
        "customers": User.objects.order_by("-date_joined")[:100],
        "subscriptions": Subscription.objects.select_related("user", "plan").order_by("-updated_at")[:100],
        "subscription_statuses": Subscription.STATUS,
        "forms": forms, "editing": entity, "edit_id": edit_id,
        "section": request.GET.get("section", "visao-geral"),
    }
    return render(request, "dashboard/manager.html", context)


@superuser_required
def manager_save(request, entity):
    if request.method != "POST" or entity not in MANAGED:
        return redirect("dashboard:manager")
    model, form_class, section = MANAGED[entity]
    object_id = request.POST.get("object_id")
    instance = get_object_or_404(model, pk=object_id) if object_id else None
    form = form_class(request.POST, request.FILES, instance=instance, prefix=entity)
    if form.is_valid():
        item = form.save()
        if entity == "version" and item.published and not item.published_at:
            item.published_at = timezone.now()
            item.save(update_fields=["published_at"])
        AuditEvent.objects.create(actor=request.user, action=f"manager.{entity}.save", target=f"{model.__name__}#{item.pk}")
        messages.success(request, "Alterações salvas com sucesso.")
        return redirect(_manager_url(section))
    messages.error(request, "Não foi possível salvar. Revise os dados informados.")
    return redirect(f'{_manager_url(section)}&edit={entity}' + (f"&id={object_id}" if object_id else ""))


@superuser_required
def manager_delete(request, entity, object_id):
    if request.method == "POST" and entity in MANAGED:
        model, _form, section = MANAGED[entity]
        item = get_object_or_404(model, pk=object_id)
        target = f"{model.__name__}#{item.pk}"
        try:
            item.delete()
            AuditEvent.objects.create(actor=request.user, action=f"manager.{entity}.delete", target=target)
            messages.success(request, "Item removido.")
        except Exception:
            messages.error(request, "Este item possui histórico vinculado. Desative-o em vez de remover.")
        return redirect(_manager_url(section))
    return redirect("dashboard:manager")


@superuser_required
def manager_user_action(request, user_id):
    if request.method == "POST":
        customer = get_object_or_404(User, pk=user_id)
        action = request.POST.get("action")
        if action == "lifetime":
            customer.lifetime_access = not customer.lifetime_access
            customer.save(update_fields=["lifetime_access"])
        elif action == "active" and customer != request.user:
            customer.is_active = not customer.is_active
            customer.save(update_fields=["is_active"])
        else:
            return redirect(_manager_url("clientes"))
        AuditEvent.objects.create(actor=request.user, action=f"manager.user.{action}", target=f"User#{customer.pk}", metadata={"enabled": getattr(customer, "lifetime_access" if action == "lifetime" else "is_active")})
        messages.success(request, "Acesso do cliente atualizado.")
    return redirect(_manager_url("clientes"))


@superuser_required
def manager_subscription_status(request, subscription_id):
    if request.method == "POST":
        subscription = get_object_or_404(Subscription, pk=subscription_id)
        status = request.POST.get("status")
        if status in {value for value, _label in Subscription.STATUS}:
            subscription.status = status
            subscription.save(update_fields=["status", "updated_at"])
            AuditEvent.objects.create(actor=request.user, action="manager.subscription.status", target=f"Subscription#{subscription.pk}", metadata={"status": status})
            messages.success(request, "Situação da assinatura atualizada.")
    return redirect(_manager_url("clientes"))
