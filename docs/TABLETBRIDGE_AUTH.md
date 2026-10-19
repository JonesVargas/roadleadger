# Autenticação RoadLedger — desktop e Android 0.8.0

## Projetos encontrados e decisão

- Site real: `C:\Users\Jones\Documents\ProjetosPython\RoadLedgerSite` (Django 5.2.17, Django REST Framework).
- Connector: `C:\Users\Jones\Documents\ProjetosPython\TabletBridge\TabletBridgeConnector`.
- Desktop: `TabletBridgePanel/tabletbridge_panel`.
- Android empacotado: `TabletBridgePanelAndroid/app/tabletbridge_panel`. A cópia antiga no diretório Android raiz não é a fonte usada pelo `pyproject.toml`.
- Mercado desktop existente: `screens/market.py`. Continua demonstração sem operações. A atualização de autenticação não copia essa tela comercial para o Android.
- Não foram encontrados AGENTS.md nos projetos inspecionados ou ancestrais consultados.

O modelo real `accounts.User` usa `email` como USERNAME_FIELD e `full_name` para exibição. `subscriptions.access.allowed_apps` atende offline/player/company (ETS2/ATS), incluindo liberação manual e vitalícia. Isso NÃO concede TabletBridge. O `api.PlayerRecruitmentProfile` é recrutamento ETS/ATS, não uma fazenda FS25; não foi reutilizado como carreira agrícola.

A API antiga de senha em `api/password_login.py` emite `licenses.ApiToken`, sem expiração/renovação limitada. Ela permanece intacta. A API nova segue a estratégia existente de tokens opacos com `secrets` e hash SHA-256, usando sessões próprias com expiração e rotação, em vez de transformar tokens antigos ou introduzir JWT/criptografia própria. Não há novas dependências.

## Autorização exata

Nova aplicação Django `tabletbridge_access`, com `AccessGrant` específico por usuário. Decisão central em `service.decision`:

1. Usuário ativo.
2. Existência do direito específico TabletBridge.
3. Não bloqueado.
4. Liberação administrativa marcada.
5. Validade ausente ou estritamente posterior ao horário do servidor.

Não é necessário nem suficiente ter assinatura Player/Empresa/Vitalícia. Esta entrega concede acesso administrativo próprio, opcionalmente com vencimento; não adiciona produto pago aos planos, pagamentos ou downloads existentes. Bloqueio é informado por código estável; motivo interno só aparece no admin.

Login, renovação e `/me/` consultam o direito atual no banco. Tokens antigos não contornam bloqueio. Sessões revogadas, senha alterada e vencimento impedem acesso. Cada login cria sessão independente; sair revoga somente aquela sessão. Para revogar todas, selecione todas as sessões do usuário no admin. Remover/bloquear direito impede todos os dispositivos; liberar novamente pode reativar sessões ainda válidas e não explicitamente revogadas. Para encerramento permanente, revogue também as sessões.

## Endpoints reais

Base de produção: `https://roadledger.com.br/api/v1/tabletbridge/`. As rotas são implementadas localmente, mas **não publicadas por esta tarefa**.

| Método / rota | Entrada | Resultado |
| --- | --- | --- |
| POST `login/` | `email`, `password`, `device_label`, `platform` (`windows`, `android`, `other`) | Tokens e perfil autorizado |
| GET `me/` | Cabeçalho `Authorization: Bearer <access_token>` | Usuário e autorização atual |
| POST `refresh/` | `refresh_token` | Novos tokens; anteriores deixam de valer |
| POST `logout/` | `refresh_token` | Revoga somente a sessão correspondente |

Exemplo de perfil sem segredos:

```json
{"user":{"id":123,"name":"Jogador","email":"jogador@example.test"},"access":{"product":"tabletbridge","status":"authorized","expires_at":null},"farm_link":null,"commerce_enabled":false}
```

Tokens são entregues somente no login/renovação. Acesso dura 600 segundos. Renovação expira 30 dias após criação, sem prorrogação a cada uso. O banco guarda apenas hashes dos tokens, datas, plataforma, rótulo e hash de autenticação de senha. Rótulo é enviado como nome genérico do aplicativo/plataforma, sem serial, hardware ou identificador pessoal.

Renovação usa transação e bloqueio da linha (`select_for_update` no PostgreSQL); no cliente, um `asyncio.Lock` coordena login/renovação/logout. Não reenviar automaticamente renovação após timeout: o servidor pode ter consumido o token. Nesse caso, uma nova autenticação pode ser necessária. Não há janela de tolerância para reutilização do refresh anterior. SQLite é suficiente para os testes sequenciais locais; validar concorrência entre processos com PostgreSQL antes da implantação.

Respostas de erro têm `{"code":"..."}`:

| HTTP | Códigos |
| --- | --- |
| 400 | `https_required` ou requisição JSON inválida do DRF |
| 401 | `invalid_credentials`, `session_expired` |
| 403 | `account_inactive`, `product_not_authorized`, `access_not_released`, `access_expired`, `access_revoked` |
| 429 | Limitação de tentativas; cliente apresenta mensagem de espera |
| 5xx | Indisponibilidade; cliente usa mensagem genérica |

Conta inativa só é distinguida quando a senha foi comprovada. Nenhuma resposta de falha contém e-mail/nome, motivo interno ou dados de assinatura. Respostas usam `Cache-Control: no-store`. Não há cookies como autenticação nessa API; login do site/CSRF ficam inalterados. Requisições públicas exigem HTTPS; não houve liberação de CORS ou desativação de certificados.

Limites: login 5/minuto/IP e endpoints de sessão 60/minuto/IP, reutilizando `SimpleRateThrottle` do DRF. Em produção configurar cache compartilhado entre workers e limitação no proxy; o cache local padrão não oferece limite global nem garantia contra rajadas concorrentes. Confirmar IP real do proxy sem confiar em X-Forwarded-For fornecido pelo cliente. Não registrar corpos, cabeçalhos Authorization, tokens, senhas ou respostas de login no proxy/APM. Decoradores de dados sensíveis protegem variáveis/POST do Django; operar produção com DEBUG=False. Não foram adicionados logs de credenciais.

## Tela e política de conexão

A inicialização mostra login ou tenta renovar a credencial recuperada. O painel só abre após resposta online autorizada. Login não depende do FS25/Connector. E-mail/senha, processamento, prevenção de envio simultâneo, senha revelável e mensagens em português. Links usam rotas reais existentes:

- `https://roadledger.com.br/conta/criar/`
- `https://roadledger.com.br/conta/senha/esqueci/`

Nome, estado liberado, validade e **Sair da conta** aparecem no menu. O nome do jogador no cadastro do Mercado desktop deriva do usuário autenticado e fica somente leitura; propriedade/CNPJ locais não passam a ser vínculos de conta.

O app consulta autorização a cada 60 segundos enquanto o painel está aberto. Falha de rede, timeout, resposta inválida ou revogação bloqueiam o painel, fecham o mapa em tela cheia e desconectam o Connector. Não há autorização offline neste preset. Uma falha temporária preserva a credencial de renovação; a tela oferece reconexão. Sessão inválida/expirada remove a credencial. A senha é limpa do formulário após cada tentativa e nunca é gravada.

Logout remoto precisa de confirmação. Em falha de rede, o painel fecha e avisa que a saída no servidor não foi confirmada; a credencial é preservada para reconectar e concluir a saída. Ao reiniciar com essa credencial, o fluxo normal tentará validar novamente. Não se afirma revogação bem-sucedida offline.

## Armazenamento por plataforma

**Windows:** refresh token protegido por DPAPI do usuário atual (sem modo de máquina), em `%USERPROFILE%/.tabletbridge-panel/session-<hash-da-origem>.dpapi`. Sem senha ou access token em disco. Troca de URL seleciona arquivo independente. Não há transferência de credencial entre dispositivos. Teste real de ida/volta executado neste Windows, verificando ausência do token em texto no arquivo. Falha de proteção ao gravar faz a sessão continuar apenas em memória; nenhum fallback em JSON.

**Android:** sessão **apenas em memória**, sem persistência de tokens. Ao fechar/reiniciar, fazer login novamente. Não foi declarado armazenamento seguro por equivalência ao desktop. `flet-secure-storage` tem suporte nativo documentado, mas não foi adicionado sem build e validação do plugin no dispositivo. Esta limitação é intencional e deve ser removida apenas após verificação no Android. `ctypes`/DPAPI é importado de forma compatível, porém nunca executado no Android. Dependências de empacotamento continuam `flet==1.0.4` e `httpx==0.28.1`, já usadas pelo APK anterior. `allowBackup=false` permanece. Cleartext existente atende somente ao Connector local; a URL pública de autenticação é validada separadamente e exige HTTPS.

## Administração

A central administrativa existente agora possui o atalho **TabletBridge / Cooperativa RoadLedger**, em `/painel/gestao/`, que abre `/painel/tabletbridge/gestao/`. Segue a regra existente da central: somente superusuário ativo. Nessa página é possível buscar players por nome/e-mail e editar liberação, bloqueio, motivo interno e validade. No Django admin, os mesmos campos também aparecem dentro do cadastro do usuário, com coluna de situação na listagem. Alterações de autorização são auditadas, sem alterar planos ETS2/ATS.

Após instalar a migração, acessar `/admin/` com usuário staff com permissões adequadas ou superusuário:

1. **Tabletbridge access → Access grants**: adicionar usuário real, marcar liberação, validade opcional; bloqueio e motivo interno quando necessário.
2. **Device sessions**: consultar usuário, rótulo, plataforma, criação, último uso, vencimento e revogação. A ação **Revogar as sessões selecionadas** exige permissão de alteração. Nenhum hash/segredo aparece nos campos administrativos.
3. Eventos de alterações/exclusões de direitos e revogação administrativa ficam em `audit.AuditEvent` e no histórico normal do Django admin, sem tokens ou senhas.

Usuários comuns não acessam essa administração. Nenhum usuário existente recebe direito novo automaticamente. Esta entrega não cria nem edita contas reais para teste.

## Testes e desenvolvimento isolado

Rodar no RoadLedgerSite com seu ambiente:

```powershell
.\.venv\Scripts\python.exe manage.py test tabletbridge_access api.test_password_login --settings=config.integration_test_settings
```

Usa banco em memória; não executa migrações no banco atual. Teste real HTTP cliente→Django disponível em `TabletBridge/integrations/roadledger/test_live_client.py` (configurar PYTHONPATH para essa pasta e para as dependências httpx do Panel). Abrange duas sessões, renovação e logout. Testes do cliente/Flet e DPAPI:

```powershell
# Dentro de TabletBridgePanel
.\.venv\Scripts\python.exe -m unittest discover -s tests
# Dentro de TabletBridgePanelAndroid/app, usando o Python de desenvolvimento desktop
..\..\TabletBridgePanel\.venv\Scripts\python.exe -m unittest discover -s ..\tests
```

Para desenvolvimento manual, `tabletbridge_dev_settings.py` da pasta de integração usa somente SQLite isolado dentro de `.local/`, com URLs localhost explícitas. Adicionar essa pasta ao PYTHONPATH; executar `manage.py migrate --settings=tabletbridge_dev_settings`, `createsuperuser` e `runserver --settings=tabletbridge_dev_settings` no site. Conceder direito no admin desse banco temporário. No terminal do Panel, definir `TABLETBRIDGE_AUTH_DEV=1` e `TABLETBRIDGE_AUTH_URL=http://127.0.0.1:8000`, depois iniciar `main.py`. Nenhum domínio externo HTTP é aceito. Não copiar esse settings para produção.

Para produção/desenvolvimento remoto, `TABLETBRIDGE_AUTH_URL` aceita origem HTTPS sem caminho/usuário/query. Padrão é o domínio público confirmado. APK compilado usa esse padrão; não colocar segredos em configurações do pacote. Login requer os endpoints publicados; a versão pública antiga do site ainda não contém esta integração.

## Implantação para revisão posterior — não executada

1. Revisar app novo, migração `tabletbridge_access/0001_initial.py`, inclusão em INSTALLED_APPS e URL `/api/v1/tabletbridge/`. Conferir testes PostgreSQL e backup/restauração de banco.
2. Revisar configuração de domínio, HTTPS do proxy, DEBUG=False, SECRET_KEY, ALLOWED_HOSTS, SSL redirect/HSTS e cache/rate limiting compartilhado. Nenhuma chave entra no cliente.
3. No procedimento aprovado de implantação do site, executar `manage.py migrate tabletbridge_access`, `check --deploy` e reiniciar serviço. Não aplicar essas ações apenas para testar o app.
4. Conceder autorização específica aos usuários de teste no admin, validar login, bloqueio durante uso, expiração e duas sessões reais.
5. Construir APK 0.8.0 com script atualizado; testar em tablet físico: teclado, layout/orientação, interrupção de rede, ciclo de vida, login/saída e coexistência com Windows. APK 0.7.1 preservado. Esta tarefa não declara build/aprovação física Android sem evidência.

## Limites e próxima etapa

Connector não foi modificado: API local continua separada, sem receber token RoadLedger. O identificador de uma visualização local não é autenticação de conta nem pareamento seguro. Login no site não autoriza automaticamente qualquer Connector encontrado na rede. Usuário ainda escolhe explicitamente endereço e porta; usar rede confiável. Uma próxima etapa deverá adicionar pareamento/consentimento local próprio, sem reaproveitar refresh tokens em tráfego LAN.

Não existe carteira, saldo online, associação automática de save, fazenda ou silo. `farm_link=null`, comércio desativado. O futuro vínculo deve usar desafio curto emitido pelo servidor para a conta autenticada, confirmado no Connector consentido e na carreira/fazenda correta; então armazenar vínculo único no servidor. Nome da fazenda/CNPJ/ID digitado não provam posse. Reservas, débitos, créditos, transferências, impostos efetivos e sincronização de dinheiro continuam fora desta entrega.

## Demandas públicas — Cooperativa RoadLedger

O pedido de produtos é um anúncio global da **Cooperativa RoadLedger**, sem destinatário específico: todos os usuários ativos, cadastrados e com autorização TabletBridge liberada e válida veem as mesmas demandas publicadas. Não há campo de duração/vencimento. Uma demanda permanece publicada até ser encerrada manualmente; não depende de uma entrega individual. Isso permite ao jogador consultar as condições para futuramente escolher entre vender no jogo e atender ao site.

Na central TabletBridge, criar uma demanda, escolher Rascunho/Publicada/Encerrada e incluir de 1 a 20 produtos. Cada produto tem nome, quantidade solicitada, unidade (L/kg/un) e **valor unitário em moedas do jogo**; o site calcula o total previsto. Por exemplo, 30.000 L a 0,80 por L = 24.000 moedas. O campo não é preço por 1.000 L. Quantidade precisa ser positiva, preço não negativo, produto/unidade não pode se repetir. Pode adicionar/remover linhas e editar uma demanda existente. Não há estoque, reserva, aceite, entrega, redução de quantidade, venda efetiva ou pagamento nessa publicação.

O player acessa pelo botão **Cooperativa RoadLedger** na área Minha conta. Página real: `/painel/tabletbridge/demandas/`, autenticada pelo login do site e autorização específica atual. Rascunhos/encerradas ficam ocultos; sem autorização recebe 403. No app, a consulta futura pode usar `GET /api/v1/tabletbridge/demands/` com Bearer TabletBridge; paginação 20 por página, comprador fixo, produtos, quantidades, unidade, preço e total, `duration=indefinite` e `commerce_enabled=false`. Esta entrega ainda não adiciona consumo dessa lista à tela Mercado do aplicativo.

Há uma segunda migração, `0002_productdemand_demanditem`, para demandas e itens. No plano aprovado de implantação, aplicar ambas as migrações do app. Modelos não possuem FK de destinatário/player nem campos de prazo. A auditoria registra o administrador e o estado salvo, sem segredos. Formulários web usam sessão/CSRF do site; API usa tokens próprios. Demandas não geram mensagens externas ou notificações.
