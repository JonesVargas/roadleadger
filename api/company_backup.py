import base64
import binascii
import hashlib
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework import serializers
from .company_api import endpoint
from .models import CompanyCloudBackup, VirtualCompany

MAX_BACKUP_BYTES = 1_500_000

@endpoint(["GET", "POST"], app="company")
def backup(request):
    if request.method == "GET":
        row = CompanyCloudBackup.objects.filter(owner=request.user).select_related("company").first()
        if not row:
            return Response({"available": False, "revision": 0})
        result = dict(available=True, revision=row.revision, company_id=row.company_id, company_name=row.company.name, updated_at=row.updated_at, sha256=row.sha256)
        if request.GET.get("download") == "1":
            result["content"] = base64.b64encode(bytes(row.content)).decode("ascii")
        return Response(result)
    encoded = request.data.get("content", "")
    if not isinstance(encoded, str) or len(encoded) > MAX_BACKUP_BYTES * 4 // 3 + 4:
        raise serializers.ValidationError("O backup excede o tamanho permitido.")
    try:
        content = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        raise serializers.ValidationError("Backup inválido.")
    if not content or len(content) > MAX_BACKUP_BYTES or hashlib.sha256(content).hexdigest() != request.data.get("sha256"):
        raise serializers.ValidationError("A integridade do backup não foi confirmada.")
    company_id = serializers.UUIDField().run_validation(request.data.get("company_id"))
    revision = request.data.get("revision")
    if type(revision) is not int or revision < 0:
        raise serializers.ValidationError("Revisão inválida.")
    with transaction.atomic():
        type(request.user).objects.select_for_update().get(pk=request.user.pk)
        company = get_object_or_404(VirtualCompany, pk=company_id, owner=request.user)
        row = CompanyCloudBackup.objects.filter(owner=request.user).first()
        if (row.revision if row else 0) != revision or (row and row.company_id != company.id):
            return Response({"detail": "Existe um backup mais recente ou de outra empresa nesta conta. Restaure-o antes de enviar novos dados."}, status=409)
        row, _ = CompanyCloudBackup.objects.update_or_create(owner=request.user, defaults=dict(company=company, content=content, sha256=hashlib.sha256(content).hexdigest(), revision=revision+1))
    return Response({"revision": row.revision, "updated_at": row.updated_at})
