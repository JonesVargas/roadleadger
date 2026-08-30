# RoadLedger Site

Site Django independente para divulgação, assinaturas, pagamentos, downloads e licenciamento do RoadLedger desktop.

## Desenvolvimento local (Windows)

1. Crie e ative o ambiente: `py -3.11 -m venv .venv` e `.venv\Scripts\activate`.
2. Instale: `python -m pip install -r requirements.txt`.
3. Copie `.env.example` para `.env` e troque `SECRET_KEY`.
4. Execute `python manage.py migrate`.
5. Execute `python manage.py seed_roadledger`.
6. Crie o administrador: `python manage.py createsuperuser`.
7. Inicie: `python manage.py runserver`.

## Mercado Pago (sandbox)

Defina `MP_ENVIRONMENT=sandbox`, `MP_ACCESS_TOKEN`, `MP_WEBHOOK_SECRET` e a URL HTTPS pública em `MP_WEBHOOK_URL`. O navegador nunca ativa uma assinatura: o webhook é autenticado, o recurso é consultado novamente na API oficial e o evento é idempotente. Os testes usam respostas simuladas; nenhuma credencial real integra o repositório.

## Arquivos e segurança

Instaladores ficam no storage configurado. Em produção, configure S3 compatível e não sirva a pasta de mídia publicamente. Cada versão calcula SHA-256, downloads exigem plano compatível, possuem limite por usuário e geram auditoria.

## Railway (preparado, não publicado)

Crie PostgreSQL, configure as variáveis de `.env.example`, e use `railway.json`. Antes de produção: SMTP real, domínio/HTTPS, storage privado, credenciais do Mercado Pago, revisão jurídica e backups. O deploy não foi executado.

## API desktop

- `POST /api/v1/device/code/`: gera código de dispositivo.
- Usuário aprova em `/licencas/ativar/`.
- `POST /api/v1/device/token/`: troca o código por token uma única vez.
- `GET /api/v1/me/`, `/entitlements/` e `/versions/latest/`: usam `Authorization: Bearer <token>`.

## Testes

`python manage.py test` e `ruff check . --exclude migrations,.venv`.

## Conteúdo jurídico

Os textos de Termos e Privacidade gerados pelo seed são modelos provisórios e precisam de revisão jurídica antes da publicação.
