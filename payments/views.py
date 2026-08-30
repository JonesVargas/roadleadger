import json

from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt

from .models import WebhookEvent
from .services import process_webhook, valid_signature


@csrf_exempt
def mercado_pago_webhook(request):
    if request.method != "POST":
        return HttpResponse(status=405)
    try:
        payload = json.loads(request.body or b"{}")
    except ValueError:
        return JsonResponse({"error": "JSON inválido"}, status=400)
    resource_id = str(payload.get("data", {}).get("id") or request.GET.get("data.id") or "")
    topic = payload.get("type") or request.GET.get("type", "")
    signature_ok = valid_signature(request, resource_id)
    if not signature_ok:
        return JsonResponse({"error": "assinatura inválida"}, status=401)
    event_key = f"{topic}:{payload.get('id') or resource_id}"
    event, created = WebhookEvent.objects.get_or_create(
        event_key=event_key,
        defaults={"topic": topic, "resource_id": resource_id, "signature_valid": True, "payload": payload},
    )
    if not created or event.processed_at:
        return JsonResponse({"status": "duplicado"})
    try:
        process_webhook(event)
    except Exception as exc:
        event.processing_error = str(exc)
        event.save(update_fields=["processing_error"])
        return JsonResponse({"status": "aceito para nova tentativa"}, status=202)
    return JsonResponse({"status": "processado"})
