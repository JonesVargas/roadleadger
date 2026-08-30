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

Defina `PAYMENT_CREDENTIALS_KEY` no servidor e mantenha essa chave estável. Depois, cadastre as credenciais de teste e produção em **Central administrativa > Pagamentos** e ative somente o ambiente desejado. Variáveis `MP_*` continuam disponíveis como fallback. O navegador nunca ativa uma assinatura: o webhook é autenticado, o recurso é consultado novamente na API oficial e o evento é idempotente. Os testes usam respostas simuladas; nenhuma credencial real integra o repositório.

## Arquivos e segurança

Instaladores ficam no storage configurado. No primeiro deploy do Railway, monte um Volume em `/data` e defina `MEDIA_ROOT=/data/media`; isso evita perder os arquivos enviados a cada nova versão. Para escalar para várias réplicas, use `DOWNLOAD_STORAGE=s3` com um bucket S3 compatível privado. Cada versão calcula SHA-256, downloads exigem plano compatível, possuem limite por usuário e geram auditoria.

## Railway (preparado, não publicado)

1. Crie um projeto a partir deste repositório GitHub e adicione um serviço PostgreSQL. O Railway detectará o `Dockerfile` automaticamente.
2. No serviço web, referencie `DATABASE_URL` com `${{Postgres.DATABASE_URL}}`.
3. Copie as variáveis de `.env.production.example` para o serviço e substitua os valores de exemplo.
4. Monte um Volume em `/data` e mantenha `DOWNLOAD_STORAGE=local` e `MEDIA_ROOT=/data/media`.
5. Gere um domínio Railway provisório; atualize `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `SITE_URL` e `MP_WEBHOOK_URL` com esse endereço.
6. Configure o healthcheck do serviço como `/api/v1/health/`, com timeout de 300 segundos.
7. Após o primeiro deploy, execute `python manage.py createsuperuser` uma única vez pelo terminal do serviço.

O `Dockerfile` coleta os arquivos estáticos na construção e, ao iniciar, executa as migrações, garante os dados iniciais e sobe o Gunicorn. O `railway.json` permanece apenas como referência para serviços legados; novos serviços do Railway devem usar o `Dockerfile` e as opções do painel. O deploy não foi executado.

Use `.env.production.example` como checklist. Gere valores longos e independentes para `SECRET_KEY` e `PAYMENT_CREDENTIALS_KEY`; não troque a segunda depois de cadastrar credenciais, pois ela é necessária para descriptografá-las. Antes da venda: configure SMTP real, credenciais do Mercado Pago, domínio/HTTPS, backups e revisão jurídica. Comece com HSTS de 3600 segundos e aumente somente depois de confirmar que domínio e subdomínios funcionam integralmente por HTTPS.

## API desktop

- `POST /api/v1/device/code/`: gera código de dispositivo.
- Usuário aprova em `/licencas/ativar/`.
- `POST /api/v1/device/token/`: troca o código por token uma única vez.
- `GET /api/v1/me/`, `/entitlements/` e `/versions/latest/`: usam `Authorization: Bearer <token>`.

## Testes

`python manage.py test` e `ruff check . --exclude migrations,.venv`.

## Conteúdo jurídico

Os textos de Termos e Privacidade gerados pelo seed são modelos provisórios e precisam de revisão jurídica antes da publicação.
