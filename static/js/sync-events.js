(() => {
  const table = document.getElementById("sync-events");
  if (!table || !window.EventSource) return;
  const status = document.getElementById("sync-status");
  const empty = document.getElementById("sync-empty");
  const seen = new Set();
  const labels = {"delivery.started":"Frete iniciado","delivery.settled":"Frete concluído",
    "delivery.cancelled":"Frete cancelado","invoice.paid":"Boleto pago",
    "setup.started":"Configuração iniciada","sync.test_completed":"Teste de conexão"};
  const source = new EventSource(table.dataset.stream);
  source.onopen = () => { status.textContent = "Conexão confirmada. Atualizações automáticas."; };
  source.onmessage = (message) => {
    let event;
    try { event = JSON.parse(message.data); } catch { return; }
    if (!event.event_id || seen.has(event.event_id)) return;
    seen.add(event.event_id);
    empty.hidden = true;
    const row = document.createElement("tr");
    [labels[event.event_type] || event.event_type, event.game,
      new Date(event.received_at).toLocaleString("pt-BR")].forEach(value => {
        const cell = document.createElement("td");
        cell.textContent = value;
        row.appendChild(cell);
      });
    table.prepend(row);
    while (table.children.length > 100) table.lastElementChild.remove();
  };
  source.onerror = () => { status.textContent = "Aguardando novas atualizações; reconexão automática."; };
  window.addEventListener("pagehide", () => source.close(), {once:true});
})();
