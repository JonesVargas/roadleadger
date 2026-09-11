# Planos e aplicativos

- Player: R$ 5,99 por mês; RoadLedger original offline e RoadLedger Player online.
- Empresa Virtual: R$ 14,99 por mês; os dois aplicativos Player e a gestão Empresa Virtual.

No painel de gestão, use **Planos e preços**. O campo **Aplicativos incluídos** define as permissões; o texto de benefícios é apenas descritivo. É possível criar outras ofertas e periodicidades escolhendo o mesmo tipo.

Em **Versões**, selecione **Aplicativo** antes de enviar o instalador. Os três aplicativos podem ter o mesmo número de versão. A restrição por códigos de planos é opcional e adicional; nunca concede um aplicativo ausente no plano.

As migrações criam as duas ofertas mensais, retiram as antigas de novas vendas e preservam assinaturas anteriores (preço, estado e acesso completo). Acesso vitalício continua incluindo os três aplicativos. Arquivos antigos são classificados pelo nome do instalador quando ele identifica Player ou Empresa; arquivos sem essa identificação permanecem como offline e podem ser corrigidos no painel.

A API de permissões retorna `apps` e aceita `?app=offline`, `?app=player` ou `?app=company`. A busca de versão também usa esse parâmetro e respeita as permissões. As operações de gestão da empresa exigem acesso ao aplicativo company; os funcionários continuam consultando vagas e contratos.

Validação: 78 testes do site e 17 do aplicativo Empresa. Testes usam contas temporárias e não efetuam cobranças reais.
