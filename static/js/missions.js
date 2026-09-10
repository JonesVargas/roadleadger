(() => {
  const game = document.getElementById('id_mission-game');
  const map = document.getElementById('id_mission-map');
  const data = document.getElementById('mission-map-options');
  if (!game || !map || !data) return;
  const maps = JSON.parse(data.textContent);
  function refresh() {
    const selected = map.value;
    map.replaceChildren(new Option('Selecione o mapa', ''));
    maps.filter(item => item.game === game.value).forEach(item => map.add(new Option(item.name, item.id)));
    if (Array.from(map.options).some(option => option.value === selected)) map.value = selected;
  }
  game.addEventListener('change', refresh);
  refresh();
})();
