# Etapa implementada — 11/09/2026

## Entregue no código local
- API de eventos autenticada, inbox idempotente e outbox transacional.
- Adaptação compatível do endpoint de fretes já existente.
- Publicação privada para player e proprietário da empresa.
- Feed REST por cursor e confirmação vinculada à instalação.
- SSE no site com retomada por Last-Event-ID e página de acompanhamento.
- Fila SQLite local com retomada, isolamento de conta, espera progressiva e limite de tentativas.
- Central de Sincronização nos dois aplicativos.
- Motor persistente de 12 etapas, com bloqueio, validação, revisão e separação por jogo.
- Livro-caixa virtual balanceado e operações internas de boleto/estorno.

## Ainda NÃO concluído
- Telas e adaptadores completos das 12 etapas: o motor está testado, mas não é o assistente final.
- Migração/conciliação de saldos legados e ativação da autoridade financeira central.
- API e telas de empréstimos, financiamentos, frota e boletos usando exclusivamente o novo livro-caixa.
- Liquidação do frete vinculada ao livro-caixa central (o fluxo anterior continua ativo).
- Progresso e recompensas das missões, multas avulsas e comandos seguros do jogo no novo protocolo.
- Validação ponta a ponta incluindo missão e saldo do jogo.
- Publicação no servidor e nova versão dos executáveis, instaladores e ZIPs.

O diagnóstico da API informa financial_authority=legacy para não anunciar uma economia
central ainda não ativada. Nenhum saldo antigo foi importado ou recalculado.
A assinatura real em Mercado Pago permanece separada do dinheiro virtual.

## Arquivos
Site:
- docs/sincronizacao-eventos.md
- road_sync/apps.py, models.py, contracts.py, service.py, views.py, urls.py
- road_sync/ledger.py, web.py, tests.py, test_ledger.py
- road_sync/migrations/0001_initial.py
- road_sync/migrations/0002_virtualaccount_virtualtransaction_virtualinvoice_and_more.py
- api/company_api.py
- config/settings.py, config/urls.py
- templates/road_sync/center.html
- templates/dashboard/home.html
- static/js/sync-events.js

Player:
- app/durable_sync.py, app/setup_state.py
- ui/sync_center.py, ui/main.py
- tests/test_event_foundation.py

Empresa:
- src/roadledger/infrastructure/durable_sync.py, setup_state.py
- src/roadledger/ui/sync_center.py, app.py
- tests/test_event_foundation.py

## Verificação realizada
- Site: 125 testes passaram (road_sync, api, subscriptions, payments, accounts, downloads, dashboard, licenses).
- Player: 6 testes de fila e assistente passaram.
- Empresa: 6 testes de fila e assistente passaram.
- Inicialização e encerramento da Central dos dois apps: passou com bancos temporários.
- Ruff dos novos módulos: passou.
- Migrações: sem divergência entre modelos e arquivos de migração.
- Banco de produção e perfis reais: não usados nos testes.

O primeiro teste gráfico do player mostrou retenção de conexão SQLite por rotinas
legadas. A tela abriu e fechou; a limpeza do diretório temporário passou após coleta
de conexões. Revisar fechamento explícito dessas conexões antes do pacote final.

## Execução de desenvolvimento
No site, usando a virtualenv existente:
```
python manage.py test road_sync api subscriptions payments accounts downloads dashboard licenses --settings=config.integration_test_settings --noinput
```
Em cada app:
```
python tests/test_event_foundation.py
```
Os testes do servidor usam banco em memória. Não aplicar migrações no banco real para testar.
As novas páginas ficam em /painel/sincronizacao/ e /api/v1/sync/.
A demonstração integrada atual usa jogo simulado nos testes de eventos, não um save real.

## Continuação — assistente visual e vínculo de perfil
Implementados os componentes visuais SetupWizard e SetupAdapter nos dois apps.
A página Configuração inicial usa progresso, campos persistentes, retorno à etapa
anterior e validação em segundo plano. Login e plano são conferidos no servidor.
Instalação/documentos, telemetria, perfil e mods têm verificações reais.
O perfil recebe um vínculo por usuário, instalação e jogo no servidor.
O diagnóstico recebe um comando sem efeito financeiro, grava o recebimento e o confirma.

Novos arquivos:
- Player: app/setup_probe.py; ui/setup_adapter.py; ui/setup_wizard.py; tests/test_setup_probe.py.
- Empresa: equivalentes em src/roadledger/infrastructure e src/roadledger/ui; tests/test_setup_probe.py.
- Site: road_sync/agent.py; road_sync/test_agent.py.
- Migração aditiva: road_sync/0003_gameprofilebinding_agentprobe_and_more.py.
- Alterados: setup_state, durable_sync, ui/main.py / ui/app.py, road_sync/models.py e urls.py.

Testes nesta continuação:
- 18 testes do módulo road_sync passaram.
- 5 testes de leitura de jogo/perfil/mods passaram em cada app.
- 6 testes de fila/estado passaram novamente na empresa.
- Tela do assistente dos dois apps: inicialização e bloqueio verificados.
- Player: persistência e retomada dos campos na tela também verificadas.

Limites que permanecem:
- O assistente ainda não é forçado na abertura; a integração final do bloqueio do
  dashboard depende de terminar os fluxos financeiros.
- Etapas de financiamento e caminhão da empresa ainda bloqueadas, sem movimentar valores.
- O resumo final não libera a nova configuração enquanto o servidor informar economia legada.
- Escolha do segundo jogo da empresa e indexação completa de mapas ainda precisam ser integradas.
- Instalação do plugin usa os serviços existentes; revisão de escrita segura ainda pendente.
- Ainda não há migração integral de empréstimos, boletos, frota e missões.
- Não publicados e não empacotados os novos executáveis.


## Continuação — 11/09/2026: caixa central e regressão

Implementado e testado, ainda sem ativação em produção:
- API privada para consultar contas/boletos e pagar boletos conciliados.
- Autorização por titular e plano; pagamento repetido mantém o mesmo lançamento.
- Pagamentos estornados ficam em revisão e não liberam crédito indevido.
- Empréstimos virtuais no servidor, com limites existentes (player 100 mil;
  empresa 500 mil), parcelas diárias reais a partir de amanhã e transação atômica.
- A dívida corresponde ao principal pendente, inclusive em pagamentos estornados.
- Consultas de auditoria no administrador; não permitem editar/apagar lançamentos.
- Fretes autônomos passam a sincronizar no ciclo de segundo plano do player;
  confirmação do site publica um evento uma única vez.
- Instalação do plugin do player usa arquivo temporário, backup verificado e
  substituição atômica, recusando a instalação se o jogo estiver aberto.
- Leituras internas do Repository do player agora fecham as conexões explicitamente.
- Assistentes recusam documentos de outro jogo e perfil fora dos documentos
  verificados. Alterar campos durante uma verificação exige nova verificação.
- Configuração de perfil da empresa separada por jogo; cadastro usa o jogo escolhido.

Arquivos desta continuação:
- Site: road_sync/finance_api.py, credit.py, admin.py, test_finance_api.py,
  test_credit.py; alterações em ledger.py, models.py, urls.py e formatação dos
  módulos road_sync; api/autonomous.py, api/test_driver_ranking.py.
- Migração aditiva: road_sync/0004_virtualinvoice_principal_virtualloan_and_more.py.
- Player: database/repository.py, integrations/ets2/manager.py, ui/main.py,
  app/setup_probe.py, ui/setup_adapter.py, ui/setup_wizard.py e testes relacionados.
- Empresa: setup_probe.py, setup_adapter.py, setup_wizard.py, ui/app.py,
  ui/operations.py e tests/test_setup_probe.py.

Resultados confirmados:
- Site: 137 testes da regressão completa passaram.
- Depois da atualização de fretes autônomos: 14 testes de ranking/API passaram.
- Empresa: 13 testes passaram; abertura do assistente e jogo inicial do cadastro
  foram conferidos com banco temporário.
- Player: regressão encontrou testes antigos da tarifa do jogo e modo offline;
  foram corrigidos para os requisitos atuais, sem relaxar validações da aplicação.
- Ruff dos novos módulos do site e dos assistentes/plugin: passou.
- Migrações sem divergência; git diff --check passou.

Pendências de liberação (não esconder nem marcar como concluídas):
1. Ligar as telas às operações financeiras centrais e migrar/conferir os saldos,
   empréstimos, frota e boletos existentes. As APIs centrais não importam saldos
   arbitrários do cliente; contas não conciliadas continuam bloqueadas.
2. Amortização e financiamento/compra de veículos no novo livro-caixa.
3. Lançar entregas, multas, despesas e recompensas de missões no mesmo livro-caixa,
   retirando a autoridade financeira local sem pagamentos duplicados.
4. Concluir etapas financeiras e bloqueio inicial dos assistentes.
5. Comandos financeiros seguros para o agente do jogo e testes ponta a ponta
   de entrega/missão/pagamento nos dois apps.
6. Publicar migrações/API e só depois gerar executáveis, instaladores e ZIPs limpos.

O diagnóstico continua informando financial_authority=legacy intencionalmente.
Os pacotes finais não foram gerados e o site não foi publicado nesta continuação.
Nenhum banco real, save real ou cadastro de produção foi alterado para testar.


### Fechamento da verificação local desta etapa
- Player: 198 casos passaram na regressão; o único caso restante era a expectativa
  antiga de abrir o modo offline. O teste passou a verificar ATS/ETS2 e rejeição do
  modo removido. Após o ajuste, 19 testes direcionados passaram, incluindo esse caso.
- O teste gráfico de compra foi isolado da confirmação humana (resposta simulada
  apenas no teste). O processo de teste que aguardava a confirmação foi encerrado;
  os aplicativos reais e os jogos não foram encerrados.
- O envio automático de fretes autônomos foi incluído no ciclo já existente;
  falha no envio de um grupo não impede a tentativa do outro grupo.
- Não há testes em execução deixados por esta etapa.


## Pacotes de validação 0.3.0-rc.1 — 11/09/2026
Foram gerados, a pedido do usuário, executável Windows, instalador e ZIP de cada
app em distribuicao/0.3.0-rc.1. Esta é uma RC de validação, não a conclusão da
migração financeira central. VERSAO.txt informa explicitamente as pendências.
Os metadados de versão e ícone estão incorporados aos executáveis e instaladores;
F1 abre a descrição da versão nos aplicativos.
O player abriu empacotado para ETS2 e ATS; a empresa abriu com as migrações locais.
Todos os bancos de teste da validação iniciaram com zero cadastros e lançamentos.
Os arquivos distribuídos não incluem bancos, tokens ou backups. ZIPs e hashes
foram verificados. Os instaladores foram compilados sem instalar por cima dos
aplicativos do usuário. Instalar a atualização preserva dados já existentes.
A publicação do servidor e a migração financeira continuam pendentes.


## Atualização de pacotes — 0.3.0-rc.2 — 11/09/2026
Concluída a retirada de botões redundantes de sincronização de perfil, empresa e vagas.
Preservados atualização de consultas, recuperação de falhas, backup e saldo do jogo.
Envio automático da empresa usa verificação do proprietário e detecção de alterações;
falhas de rede ou importação local não interrompem tentativas posteriores.
Regressão: 201 testes do player e 16 da empresa passaram. Teste direcionado confirmou
recuperação após falha local. Executáveis abriram em pastas isoladas (player ETS2 e ATS).
Bancos temporários vazios verificados. Instaladores compilados com metadados rc.2;
não instalados por cima dos apps reais. ZIPs e SHA-256 verificados.
Pacotes em distribuicao/0.3.0-rc.2 em cada projeto, sem bancos, tokens ou cadastros.
Esta entrega atualiza os pacotes de validação; NÃO conclui a migração financeira central,
o assistente obrigatório nem os comandos financeiros por evento. Site não publicado.
