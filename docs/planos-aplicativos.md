# Planos e aplicativos

- Player: R$ 5,99 por mês; RoadLedger original offline e RoadLedger Player online.
- Empresa Virtual: R$ 14,99 por mês; os dois aplicativos Player e a gestão Empresa Virtual.

No painel de gestão, use **Planos e preços**. O campo **Aplicativos incluídos** define as permissões; o texto de benefícios é apenas descritivo. É possível criar outras ofertas e periodicidades escolhendo o mesmo tipo.

Em **Versões**, selecione **Aplicativo** antes de enviar o instalador. Os três aplicativos podem ter o mesmo número de versão. A restrição por códigos de planos é opcional e adicional; nunca concede um aplicativo ausente no plano.

As migrações criam as duas ofertas mensais, retiram as antigas de novas vendas e preservam assinaturas anteriores (preço, estado e acesso completo). Acesso vitalício continua incluindo os três aplicativos. Arquivos antigos são classificados pelo nome do instalador quando ele identifica Player ou Empresa; arquivos sem essa identificação permanecem como offline e podem ser corrigidos no painel.

A API de permissões retorna `apps` e aceita `?app=offline`, `?app=player` ou `?app=company`. A busca de versão também usa esse parâmetro e respeita as permissões. As operações de gestão da empresa exigem acesso ao aplicativo company; os funcionários continuam consultando vagas e contratos.

Validação: 78 testes do site e 17 do aplicativo Empresa. Testes usam contas temporárias e não efetuam cobranças reais.

## Liberação pelo administrador

Em **Clientes**, busque por nome ou e-mail e clique em **Liberar plano**. Escolha Player ou Empresa Virtual e um prazo de 30, 90 ou 365 dias, ou sem vencimento. **Salvar liberação** concede os aplicativos sem criar assinatura ou cobrança. **Revogar liberação manual** remove somente esse acesso extra; assinaturas pagas e o acesso vitalício continuam valendo. O histórico administrativo registra quem liberou ou revogou.

O site verifica o vencimento a cada acesso. A liberação também permite ativar dispositivos e baixar os aplicativos do plano. A conta do cliente mostra o plano liberado e seu prazo. No aplicativo, use Atualizar perfil e assinatura para buscar a alteração; a tolerância offline já existente do aplicativo permanece.

## Troca de plano pelo assinante

Em Minha conta ou Pagamentos, use **Trocar plano ou renovar**. A tela compara os aplicativos, calcula a diferença com os dias restantes do período pago e exige confirmação. O upgrade é aplicado somente após o pagamento aprovado. No downgrade, a diferença vira crédito: reduz a próxima cobrança e, quando quita um ciclo completo, antecipa a quitação desse ciclo e adia a próxima cobrança. Não há reembolso automático.

A cobrança proporcional usa Checkout Pro. A atualização da recorrência usa o endpoint documentado de assinaturas do Mercado Pago. A renovação automática abate o crédito uma vez e restaura o valor normal no ciclo seguinte. PIX exige confirmação de renovação pelo assinante ao terminar o período. Acesso gratuito do administrador é independente.

Checkouts de troca valem por até 30 minutos, limitados pelo fim do ciclo atual. A diferença é confirmada no servidor; pagamentos repetidos não aplicam a troca duas vezes. Em falha ao atualizar a recorrência, a troca fica em Concluindo troca e pode ser retomada sem outro pagamento. Divergências de ciclo ou preço após um pagamento ficam registradas para conciliação, preservando o plano atual.

Referências usadas na integração:
- https://www.mercadopago.com.br/developers/pt/docs/subscriptions/subscription-management
- https://www.mercadopago.com.br/developers/pt/reference/online-payments/subscriptions/get-authorized-payment/get

Os testes de cobrança usam respostas simuladas; não efetuam pagamentos reais.
