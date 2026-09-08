# Propostas diretas de emprego

## Player

A Visão geral do RoadLedgerPlayer consulta a API a cada 30 segundos enquanto a página está aberta. O player deve conectar sua conta em Conectar conta do site e concluir a autorização do computador. A preferência começa desativada e só muda na interface após confirmação do servidor. Nome e ID vêm da conta autenticada, não do banco local. Desativar novas propostas não apaga ofertas já recebidas.

## Contrato da API para o aplicativo da empresa

Autenticação: token Bearer do proprietário.

- GET /api/v1/my/recruitment-profile/: ID público estável, nome e disponibilidade do próprio player.
- PUT /api/v1/my/recruitment-profile/: objeto com open_to_offers (booleano).
- GET /api/v1/companies/{company_id}/players/?q={nome_ou_uuid}: busca limitada a 30 players disponíveis; somente o dono dessa empresa pode pesquisar.
- POST /api/v1/companies/{company_id}/job-offers/: player_id (UUID da busca), vacancy_id (vaga da empresa) e own_truck (booleano). O nome serve à pesquisa; o envio sempre usa o ID exato, evitando homônimos.
- GET /api/v1/my/job-offers/: ofertas da conta autenticada.
- POST /api/v1/my/job-offers/{offer_id}/respond/: decision accept ou decline; aceitar exige accepted_terms true.

A proposta preserva regras e comissão no contrato. O aceite exige vaga aberta, capacidade disponível e ausência de outro vínculo ativo. Repetições e respostas por outro jogador são rejeitadas. Nesta etapa uma mesma vaga não pode gerar outra candidatura/proposta para o mesmo player após recusa; publique outra vaga quando necessário.

## Implantação e limites

Aplicar a migração api/0002 antes de usar as novas rotas. Esta alteração não foi publicada automaticamente. A tela de envio no aplicativo da empresa ainda precisa consumir os endpoints acima. Capacidade de contratação e criação/sincronização das empresas continuam dependendo da integração das melhorias descrita em INTEGRACAO_EMPRESAS.md.

O app reconhece contratos ativos do site para apresentar a comissão e evitar pagar como autônomo um jogador já contratado. O envio de fretes de funcionários, a sincronização financeira e a recuperação automática dos fretes locais pendentes continuam sendo etapas separadas. Não distribuir como versão final antes de testar o fluxo completo em dois computadores.
