from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand
from django.utils import timezone

from core.legal_content import LEGAL_VERSION, PRIVACY_PT_BR, TERMS_PT_BR
from core.models import FAQ, Feature, LegalPage, ServiceStatus, UpdatePost
from subscriptions.models import Plan


class Command(BaseCommand):
    help = "Cria os dados iniciais idempotentes do RoadLedger Site."

    def handle(self, *args, **kwargs):
        plans = [
            ("fundador", "Fundador", 9.90, "month", True, 100, True),
            ("mensal", "Mensal", 14.90, "month", False, None, False),
            ("anual", "Anual", 99.90, "year", False, None, True),
        ]
        rights = [
            "Economia e banco virtual",
            "Contratos e carreira",
            "Perfis separados ETS2/ATS",
            "Atualizações e suporte",
        ]
        for code, name, price, interval, founder, limit, featured in plans:
            Plan.objects.get_or_create(
                code=code,
                defaults={
                    "name": name,
                    "price": price,
                    "interval": interval,
                    "founder": founder,
                    "subscriber_limit": limit,
                    "featured": featured,
                    "active": True,
                    "description": "Acesso completo ao RoadLedger durante a vigência.",
                    "entitlements": rights,
                },
            )
        features = [
            ("Economia conectada", "Acompanhe banco, despesas, salários e comissões."),
            ("Carreira viva", "Evolua entre funcionário, agregado, autônomo e empresário."),
            ("Contratos", "Receba propostas e cumpra regras empresariais."),
            ("Frota e equipe", "Administre veículos, sedes e funcionários."),
            ("ETS2 e ATS", "Mantenha perfis independentes em cada jogo."),
            ("Telemetria", "Use dados do jogo para enriquecer sua operação."),
        ]
        for i, (title, description) in enumerate(features):
            Feature.objects.get_or_create(
                title=title, defaults={"description": description, "order": i, "active": True}
            )
        faqs = [
            (
                "O RoadLedger modifica o jogo?",
                "Ele complementa a experiência e sincroniza apenas funções documentadas pelo aplicativo.",
            ),
            ("Preciso de assinatura ativa?", "Sim, para downloads e autorização do aplicativo desktop."),
            (
                "ETS2 e ATS compartilham o mesmo perfil?",
                "Não. Os perfis permanecem separados para evitar conflitos.",
            ),
            (
                "O plano Fundador é limitado?",
                "Sim. São 100 assinaturas, reservadas de forma segura durante o checkout.",
            ),
        ]
        for i, (q, a) in enumerate(faqs):
            FAQ.objects.get_or_create(question=q, defaults={"answer": a, "order": i, "active": True})
        LegalPage.objects.get_or_create(
            kind="terms", defaults={"version": LEGAL_VERSION, "body": TERMS_PT_BR}
        )
        LegalPage.objects.get_or_create(
            kind="privacy", defaults={"version": LEGAL_VERSION, "body": PRIVACY_PT_BR}
        )
        for name in ["Site", "API de licenciamento", "Downloads", "Pagamentos"]:
            ServiceStatus.objects.get_or_create(
                name=name, defaults={"status": "operational", "message": "Operação normal."}
            )
        UpdatePost.objects.get_or_create(
            slug="roadledger-site-em-preparacao",
            defaults={
                "title": "RoadLedger Site em preparação",
                "summary": "A nova central de contas e assinaturas está sendo preparada.",
                "body": "Cadastros, pagamentos, licenças e downloads em um único lugar.",
                "published_at": timezone.now(),
                "active": True,
            },
        )
        for name in ["Financeiro", "Suporte", "Conteúdo", "Gerenciador de versões"]:
            Group.objects.get_or_create(name=name)
        self.stdout.write(self.style.SUCCESS("Dados iniciais criados/atualizados."))
