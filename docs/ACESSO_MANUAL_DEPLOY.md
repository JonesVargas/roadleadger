# Acesso manual e distribuição

Em **Gestão → Versões**, escolha a edição, a plataforma e o canal. Informe a versão e as notas, envie o instalador ou APK e marque **Disponível para download**. Desmarque a opção para ocultar a versão. A publicação mais recente por edição, plataforma e canal recebe o indicador **versão oferecida**. Em **Editar nomes e descrições dos aplicativos**, use o cadastro existente no Django Admin.

Em **Gestão → Acessos de usuários**, procure por nome ou pelo e-mail usado no login. Clique em **Liberar** ou **Revogar** na edição desejada. A validade é opcional. RoadLedger Offline, Player e Empresa Virtual mantêm as chaves de acesso que os clientes instalados já usam. TabletBridge Windows e Android compartilham a liberação TabletBridge. Os controles de propriedade de empresas continuam na gestão de clientes.

A área do usuário oferece arquivos pelo endpoint autenticado de download. Os instaladores são enviados ao armazenamento já configurado e o site entrega o conteúdo sem redirecionar para URLs do armazenamento. Configure um volume persistente em `/data` com `MEDIA_ROOT=/data/media` ou mantenha o bucket S3 compatível privado. Para um arquivo legado público fora do site, copie o objeto para o armazenamento privado, aponte a versão para a cópia e retire a exposição na origem. A rota autenticada só controla arquivos que passam por ela.

Para retirar o acesso a todo o RoadLedger, use **Revogar todas as edições RoadLedger**. Clientes antigos que consultam a licença sem identificar a edição continuam recebendo a decisão agregada do RoadLedger. Validações online por edição consultam a liberação atual. Uma verificação offline já gravada por um cliente antigo segue o prazo de cache implementado por esse cliente.

## Verificações de implantação

1. Confirme que o serviço web Railway está vinculado a `JonesVargas/roadleadger`, branch `main`, e que o serviço usa PostgreSQL e um volume persistente para os instaladores ou S3 privado. Confirme que os arquivos publicados existem no armazenamento e que o servidor ou bucket rejeita o caminho direto sem credenciais.
2. Consulte no banco as assinaturas com provedor recorrente e identificador externo, incluindo pendentes e pausadas, mantendo os identificadores em ambiente restrito. Confronte com a conta de produção do Mercado Pago em consulta somente leitura. Use a busca paginada de assinaturas e o estado das recorrências do RoadLedger. Desligar o webhook do site deixa de atualizar a permissão local, enquanto o provedor continua administrando o cronograma das recorrências existentes. Qualquer alteração no provedor depende de autorização própria.
3. Obtenha um backup novo do PostgreSQL (`pg_dump --format=custom` ou mecanismo de backup do Railway), proteja o arquivo e restaure-o em uma instância PostgreSQL isolada com `pg_restore --exit-on-error` ou pela ferramenta de restauração do Railway. Compare contagens de contas, assinaturas, pagamentos, versões e dados de sincronização. Registre a referência do backup, a revisão atualmente publicada e o resultado da restauração. Confirme também que os arquivos de distribuição têm cópia recuperável.
4. Na cópia restaurada, execute `python manage.py migrate --noinput` e compare os acessos válidos anteriores com os novos registros, edição e vencimento. Use contas de teste para validar login, licença, sincronização, criação e ocultação de versão, download autorizado e revogação isolada. Antes da migração final, interrompa as entradas de checkout e webhook do serviço anterior e drene requisições de cobrança em andamento, para que o conjunto de acessos a converter fique estável. Se essa janela ou qualquer validação anterior não puder ser garantida, mantenha a versão em produção.
5. Publique a revisão validada pelo fluxo GitHub → Railway. A configuração do repositório executa `collectstatic`, `migrate --noinput` e o health check de `/api/v1/health/`. Confirme no serviço publicado o hash da revisão, a saúde, login do administrador, as duas áreas de gestão e o download com uma conta de teste. Valide também que a mesma URL de download falha para outra conta sem acesso.

## Reversão

As três migrações são aditivas. Elas mantêm as contas, o histórico comercial, as permissões originais e os dados de jogo. Para corrigir uma falha da aplicação após o corte, mantenha a tabela de liberações, as alterações administrativas e a barreira de pagamentos. Reaplique uma revisão compatível com esse esquema. A reversão de imagem para uma revisão anterior ao modo manual exige manter o serviço em manutenção com as rotas de cobrança indisponíveis, pois o código anterior usa o histórico comercial para decidir o acesso. Exporte e reconcilie eventuais alterações de acesso feitas após o corte antes de voltar a abrir o site. Evite reverter o esquema ou restaurar o backup sobre um banco com gravações posteriores sem reconciliá-las.

Para uma futura reativação comercial planejada, `ROADLEDGER_MANUAL_APP_ACCESS=False` volta a habilitar a política e as rotas anteriores. Faça essa mudança somente depois de reconciliar os acessos concedidos no modo manual, verificar as credenciais e revisar a conta do provedor.

## Testes locais

- Modo manual padrão: `python manage.py test dashboard.test_manual_distribution`
- Regressão do modo anterior e testes do modo manual: execute `python manage.py test` com `ROADLEDGER_MANUAL_APP_ACCESS=False`. Os casos do modo manual ativam a configuração explicitamente.
- Consistência do esquema: `python manage.py makemigrations --check --dry-run`

Documentação do provedor: https://www.mercadopago.com.br/developers/pt/reference/online-payments/subscriptions/overview
