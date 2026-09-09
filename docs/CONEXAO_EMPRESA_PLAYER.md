# Conectar empresa e player ao site

## Empresa

1. Abra Minha empresa > Propostas e fretes no site.
2. Conecte a conta do proprietário usando o token de integração gerado no site. O token é armazenado criptografado pelo Windows.
3. Clique em Sincronizar empresa e vagas. A capacidade vem das melhorias locais e as regras atuais são enviadas para novos contratos; contratos assinados mantêm os termos anteriores.
4. Busque pelo nome ou ID, selecione o player e uma vaga e envie a proposta. O player precisa estar aberto a propostas.
5. Use Consultar fretes dos funcionários no site para importar a participação da empresa nas finanças locais. Repetir a consulta não duplica receitas. Nenhum valor é creditado ao proprietário por esse fluxo.

## Player

Autorize a conta em Visão geral > Conectar conta do site. Ative Aberto a propostas. Aceite e assine os termos da oferta desejada. Depois de receber o contrato, a telemetria grava o início e o fim dos fretes na fila local. O envio em segundo plano continua em qualquer página; novas tentativas ocorrem após falhas de conexão. A comissão líquida recebida do site entra uma única vez no histórico e nas finanças do player.

O app da empresa pode estar fechado durante as entregas: o site recebe os eventos. A empresa consulta/importa os fretes quando voltar a abrir o painel.

## Verificação e publicação

Aplicar a migração api/0004 antes de abrir as novas rotas. Foram feitos testes automatizados da API, fila com reinício, lançamento único da comissão e lançamento único da receita da empresa. Ainda é necessário testar com dois computadores, contas reais e telemetria do jogo antes de distribuir uma versão final.

A integração atual usa o proprietário como fonte das configurações da empresa local. Não é um mecanismo antitrapaça: a telemetria ainda é declarada pelo aplicativo. O fechamento financeiro do frete usa as regras atualmente implementadas na API.
