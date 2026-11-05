from functools import wraps

from django.conf import settings
from django.http import HttpResponseGone


def billing_view(view):
    @wraps(view)
    def guarded(request, *args, **kwargs):
        if settings.MANUAL_APP_ACCESS:
            return HttpResponseGone("O acesso aos aplicativos é liberado pela administração.")
        return view(request, *args, **kwargs)
    return guarded


def billing_operation(operation):
    @wraps(operation)
    def guarded(*args, **kwargs):
        if settings.MANUAL_APP_ACCESS:
            raise ValueError("Cobranças e alterações do provedor estão desativadas.")
        return operation(*args, **kwargs)
    return guarded
