# RoadLedger Site

Site Django para divulgação, liberação de acesso, downloads e licenciamento do RoadLedger e do TabletBridge.

## Desenvolvimento local (Windows)

1. Crie e ative o ambiente: `py -3.11 -m venv .venv` e `.venv\Scripts\activate`.
2. Instale: `python -m pip install -r requirements.txt`.
3. Copie `.env.example` para `.env` e troque `SECRET_KEY`.
4. Execute `python manage.py migrate`.
5. Execute `python manage.py seed_roadledger`.
6. Crie o administrador: `python manage.py createsuperuser`.
7. Inicie: `python manage.py runserver`.

## Liberação de aplicativos

Use **Gestão → Versões** para publicar arquivos e **Gestão → Acessos de usuários** para liberar as contas. O modo padrão dispensa credenciais do Mercado Pago. O histórico comercial permanece no banco. Consulte o [procedimento de implantação e reversão](docs/ACESSO_MANUAL_DEPLOY.md).

## Arquivos e segurança

Instaladores ficam no armazenamento privado configurado. No Railway, monte um volume em `/data` e defina `MEDIA_ROOT=/data/media` para preservar os arquivos entre publicações. Para escalar para várias réplicas, use `DOWNLOAD_STORAGE=s3` com um bucket compatível privado. Os downloads exigem liberação, possuem limite por usuário e geram auditoria.

## Railway

1. Crie um projeto a partir deste repositório GitHub e adicione um serviço PostgreSQL. O Railway detectará o `Dockerfile` automaticamente.
2. No serviço web, referencie `DATABASE_URL` com `${{Postgres.DATABASE_URL}}`.
3. Copie as variáveis de `.env.production.example` para o serviço e substitua os valores de exemplo.
4. Monte um Volume em `/data` e mantenha `DOWNLOAD_STORAGE=local` e `MEDIA_ROOT=/data/media`.
5. Configure o domínio e atualize `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` e `SITE_URL` com esse endereço.
6. Configure o healthcheck do serviço como `/api/v1/health/`, com timeout de 300 segundos.
7. Após o primeiro deploy, execute `python manage.py createsuperuser` uma única vez pelo terminal do serviço.

O fluxo executa a coleta de arquivos estáticos e as migrações antes de servir a aplicação pelo Gunicorn. Execute `seed_roadledger` manualmente apenas na primeira instalação. Em uma instância existente, siga o [procedimento de implantação](docs/ACESSO_MANUAL_DEPLOY.md) antes de enviar mudanças à branch de produção.

Use `.env.production.example` para configurar HTTPS, e-mail e persistência. Guarde a chave `PAYMENT_CREDENTIALS_KEY` anterior se houver credenciais históricas criptografadas para uma futura reativação.

## API desktop

- `POST /api/v1/device/code/`: gera código de dispositivo.
- Usuário aprova em `/licencas/ativar/`.
- `POST /api/v1/device/token/`: troca o código por token uma única vez.
- `GET /api/v1/me/`, `/entitlements/` e `/versions/latest/`: usam `Authorization: Bearer <token>`.

## Testes

Veja os [comandos de teste](docs/ACESSO_MANUAL_DEPLOY.md#testes-locais) do modo manual e da regressão do fluxo anterior.

## Conteúdo jurídico

Os textos de Termos e Privacidade gerados pelo seed são modelos provisórios e precisam de revisão jurídica antes da publicação.


## Integração TabletBridge 0.8.0 (local, não implantada)

Nova API independente em `/api/v1/tabletbridge/`: login por e-mail, perfil, renovação e saída. Direito administrativo específico em `tabletbridge_access.AccessGrant`; assinaturas/vitalício ETS2/ATS não concedem TabletBridge automaticamente. Sessões opacas independentes por dispositivo, acesso 10 minutos, renovação 30 dias e revogação no banco.

Ver [documentação completa](docs/TABLETBRIDGE_AUTH.md) para regras, administração, testes, armazenamento Windows/Android, limitações e procedimento de implantação/migração para revisão. Nenhum deploy ou migração no banco atual foi executado nesta entrega.
