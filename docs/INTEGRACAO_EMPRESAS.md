# API de empresas: primeira etapa

A API autenticada em `/api/v1/` oferece empresas, vagas, candidaturas, contratos com aceite, desligamento e recebimento de eventos de fretes. O ranking público considera apenas fretes concluídos, ordenados por entregas e depois quilômetros acumulados.

## Publicação

Execute `python manage.py migrate --noinput` antes de iniciar o site. Docker e Railway já incluem essa etapa. A migração cria tabelas novas; não importa os bancos dos aplicativos.

## Limites desta etapa

Os aplicativos ainda precisam ser conectados a estas rotas, incluindo fila persistente de envio e identificação do motorista. A ponte local existente não é substituída automaticamente. Empresas novas começam sem vagas de contratação liberadas (capacidade zero); a integração das melhorias ainda está pendente.

Os eventos recebidos precisam de token válido e contrato assinado. O servidor valida sequência, vínculo e repetição de identificadores. As medidas de velocidade, distância e multas ainda são declaradas pelo cliente; isso não constitui comprovação independente da telemetria. A comissão desta primeira versão usa a receita bruta; a integração dos demais custos operacionais está pendente.

## Verificação

`python manage.py test --settings=config.integration_test_settings --noinput`

A configuração de testes usa banco SQLite em memória. A implantação também deve ser verificada no banco de produção após publicação.
