(() => {
  const button = document.getElementById("copy-token");
  const code = document.getElementById("created-token");
  const status = document.getElementById("copy-token-status");
  if (!button || !code || !status) return;
  button.addEventListener("click", async () => {
    const token = code.textContent.trim();
    button.disabled = true;
    try {
      await navigator.clipboard.writeText(token);
      status.textContent = "Token copiado! Cole no aplicativo.";
      button.textContent = "Copiar novamente";
    } catch {
      const range = document.createRange();
      range.selectNodeContents(code);
      const selection = window.getSelection();
      if (selection) {
        selection.removeAllRanges();
        selection.addRange(range);
      }
      status.textContent = "O navegador não permitiu copiar automaticamente. O token foi selecionado: pressione Ctrl+C para copiar.";
    } finally {
      button.disabled = false;
    }
  });
})();
