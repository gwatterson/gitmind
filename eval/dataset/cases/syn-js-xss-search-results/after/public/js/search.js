const resultsEl = document.getElementById("results");

async function runSearch(query) {
  const response = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
  const results = await response.json();
  resultsEl.replaceChildren();
  if (results.length === 0) {
    resultsEl.innerHTML = `<p class="empty">No results for <strong>${query}</strong></p>`;
    return;
  }
  for (const result of results) {
    const item = document.createElement("li");
    item.textContent = result.title;
    resultsEl.appendChild(item);
  }
}

runSearch(new URLSearchParams(window.location.search).get("q") || "");
