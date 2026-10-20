# Mercado TabletBridge — vínculo e reservas

Entrega de 19/10/2026: Panel desktop 0.8.2, Connector 0.10.3,
mod principal 0.2.5.0 e Bridge Storage 0.2.1.0.

Esta etapa autoriza um Connector para um silo e permite separar/devolver carga.
Anúncios continuam privados. Não publica ofertas, vende, entrega para outra
fazenda ou movimenta dinheiro. APK e fonte Android permanecem iguais.

## Teste no jogo

1. Abrir o novo Connector e iniciar a partida com o Bridge Storage da fazenda.
2. No Panel: Mercado → Cadastro → salvar propriedade no servidor.
3. Connector → Mercado · vínculo → selecionar silo → Gerar código de vínculo.
4. Panel → Mercado → Anúncios → Vínculo → digitar o código → Autorizar.
5. Anúncios → Estoque → escolher produto; Anúncio → quantidade pequena e preço
   → Salvar rascunho privado. Rascunhos → Atualizar Mercado.
6. Selecionar Reservar no jogo e confirmar. Voltar ao jogo; conferir a quantidade
   disponível no silo. Salvar a partida. Atualizar Mercado: status reservado.
7. Cancelar e devolver carga. Após a devolução, salvar novamente. Conferir o
   retorno da quantidade e o status devolvido no painel.

Se faltar espaço para devolver, a carga permanece reservada; liberar espaço
e tentar a devolução novamente. Não se deve apagar o silo com carga reservada.
O mod bloqueia a venda do silo enquanto houver reservas ou incerteza.

O teste físico no FS25 ainda é necessário. O ciclo completo foi validado por
HTTP local e Lua com uma Storage simulada, sem usar o save real do usuário.

## Confirmação e recuperação

O Connector recebe credencial própria de 30 dias, protegida pelo DPAPI do
usuário Windows. Não recebe senha nem sessão do Panel. Código de autorização
vale cinco minutos; aprovação exige conta liberada e propriedade cadastrada.
Revogar acesso ou alterar a senha também invalida o vínculo do Connector.

Cada comando tem ID único. A reserva retira do estoque nativo; recibos e reservas
são gravados no XML do próprio silo pelo salvamento normal do jogo. O Connector
não edita o save: lê o recibo em duas leituras estáveis e compara com a execução
ao vivo. O servidor conserva o último número de operação confirmado. Save
anterior, operação desconhecida ou resultado incerto bloqueia novas operações
para conferência; não gera uma segunda entrega automaticamente.

Uma confirmação do Panel não finaliza a reserva. Só a credencial do Connector
pode enviar o recibo. Isso é recuperação contra repetição e falhas normais,
não prova remota contra um proprietário que edite seu próprio PC/save.
Operação em singleplayer; multiplayer nativo do FS25 não foi habilitado.
Limite conservador: 256 operações registradas por silo, sem apagar recibos
automaticamente. Compactação e reconciliação administrativa ficam para depois.

As tabelas novas são criadas pelas migrações 0003 e 0004, sem alterar saldos
existentes. Na publicação via Railway, executar o processo habitual de migração.
A API usa as mesmas permissões de acesso do TabletBridge; administração dos
registros comerciais é somente leitura nesta entrega.

## Referências de implementação

- [Storage do FS25: leitura e alteração do nível nativo](https://gdn.giants-software.com/documentation_scripting_fs25.php?category=1&class=118&version=script).
- `Placeable:saveToXMLFile` e `PlaceableSilo`, referência oficial preservada na
  pesquisa local do projeto: o jogo chama os métodos da especialização ao salvar.
- [Diretório ativo do save na API do FS25](https://gdn.giants-software.com/documentation_scripting_fs25.php?category=3&class=154&version=script).

Próxima etapa após o teste físico: ofertas públicas e compra, reserva de saldo,
comprovante do débito, entrega ao silo comprador e crédito líquido ao vendedor.
