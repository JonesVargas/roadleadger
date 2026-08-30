from django.conf import settings
from django.contrib import messages
from django.core.mail import send_mail
from django.shortcuts import get_object_or_404, redirect, render

from subscriptions.models import Plan

from .models import FAQ, Feature, LegalPage, ServiceStatus, UpdatePost


def home(request):
    return render(
        request,
        "core/home.html",
        {
            "features": Feature.objects.filter(active=True)[:6],
            "plans": Plan.objects.filter(active=True),
            "updates": UpdatePost.objects.filter(active=True)[:3],
        },
    )


def features(request):
    return render(request, "core/features.html", {"features": Feature.objects.filter(active=True)})


def how_it_works(request):
    return render(request, "core/how.html")


def updates(request):
    return render(request, "core/updates.html", {"updates": UpdatePost.objects.filter(active=True)})


def faq(request):
    return render(request, "core/faq.html", {"faqs": FAQ.objects.filter(active=True)})


def status(request):
    return render(request, "core/status.html", {"services": ServiceStatus.objects.all()})


def legal(request, kind):
    return render(request, "core/legal.html", {"page": get_object_or_404(LegalPage, kind=kind)})


def contact(request):
    if request.method == "POST":
        send_mail(
            f"Contato RoadLedger: {request.POST.get('subject', 'Sem assunto')}",
            request.POST.get("message", ""),
            settings.DEFAULT_FROM_EMAIL,
            [settings.DEFAULT_FROM_EMAIL],
        )
        messages.success(request, "Mensagem enviada.")
        return redirect("core:contact")
    return render(request, "core/contact.html")
