
const form = document.querySelector("#search-form");
const queryInput = document.querySelector("#query");
const locationInput = document.querySelector("#location");
const includeUsed = document.querySelector("#include-used");
const forceSample = document.querySelector("#force-sample");
const sampleWrap = document.querySelector("#sample-wrap");
const go = document.querySelector("#go");
const note = document.querySelector("#form-note");
const pill = document.querySelector("#mode-pill");
const banner = document.querySelector("#banner");
const errorBox = document.querySelector("#error");
const results = document.querySelector("#results");

let keyPresent = false;

function money(offer) {
  return offer.price_display || "";
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

async function loadStatus() {
  const response = await fetch("/api/status");
  const status = await response.json();
  keyPresent = Boolean(status.has_key);
  pill.hidden = false;
  if (keyPresent) {
    pill.textContent = "Live key detected";
    pill.className = "pill live";
    forceSample.checked = false;
    sampleWrap.hidden = false;
    note.textContent = "A SERPAPI_KEY is set. Each new live search uses one free-plan credit unless SerpApi serves it from cache. Tick sample data to avoid a call.";
  } else {
    pill.textContent = "Sample data · no API key";
    pill.className = "pill sample";
    forceSample.checked = true;
    forceSample.disabled = true;
    note.textContent = "No SERPAPI_KEY in the environment, so every search uses labeled sample data. Set the key and restart to compare live Indian prices. No card and no paid plan are required.";
  }
}

function row(offer, winner) {
  const bits = [offer.delivery, offer.tag].filter(Boolean).join(" · ");
  const rating = offer.rating ? `${offer.rating}★` : "";
  const link = offer.link
    ? ` <a href="${escapeHtml(offer.link)}" target="_blank" rel="noreferrer">View</a>`
    : "";
  return `<tr class="${winner ? "winner" : ""}">
    <td>${escapeHtml(offer.retailer)}${winner ? '<span class="tag">Cheapest</span>' : ""}${link}</td>
    <td>${escapeHtml(offer.title)}</td>
    <td>${escapeHtml(bits)}</td>
    <td>${escapeHtml(rating)}</td>
    <td class="right">${escapeHtml(money(offer))}</td>
  </tr>`;
}

function render(data) {
  errorBox.hidden = true;
  banner.hidden = false;
  banner.textContent = data.disclaimer || "";
  if (!data.cheapest) {
    results.hidden = false;
    results.innerHTML = `<article class="hero"><p class="kicker">No in-stock new offer</p><h2>Nothing to buy from this page of results</h2><p class="meta">Out-of-stock, unpriced, non-INR, and second-hand listings are kept out of the winner unless you include used items.</p></article>`;
    if (data.excluded && data.excluded.length) results.innerHTML += excludedTable(data.excluded);
    return;
  }
  const winner = data.cheapest;
  const gap = data.gap_to_next
    ? `<p class="gap">${escapeHtml(data.gap_to_next.amount_display)} under ${escapeHtml(data.gap_to_next.versus)} (${escapeHtml(data.gap_to_next.percent)}% less)</p>`
    : `<p class="gap">Only one in-stock retailer on this page</p>`;
  const spread = data.spread_to_highest
    ? ` Highest compared price is ${escapeHtml(data.spread_to_highest.amount_display)} more at ${escapeHtml(data.spread_to_highest.versus)}.`
    : "";
  const rows = data.retailers.map((offer) => row(offer, offer.retailer === winner.retailer && offer.price === winner.price)).join("");
  results.hidden = false;
  results.innerHTML = `
    <article class="hero">
      <p class="kicker">${data.sample ? "Sample winner" : "Cheapest in stock"}</p>
      <h2>${escapeHtml(winner.retailer)}</h2>
      <p class="price">${escapeHtml(money(winner))}</p>
      <p class="meta">${escapeHtml(winner.title)} · ${escapeHtml(data.location)} · ${data.counts.in_stock_compared} retailer${data.counts.in_stock_compared === 1 ? "" : "s"} compared.${escapeHtml(spread)}</p>
      ${gap}
    </article>
    <div class="table-wrap">
      <table>
        <thead><tr><th>Retailer</th><th>Listing</th><th>Notes</th><th>Rating</th><th class="right">Price</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
    ${data.excluded && data.excluded.length ? excludedTable(data.excluded) : ""}
  `;
}

function excludedTable(offers) {
  const rows = offers.slice(0, 12).map((offer) => {
    const why = !offer.in_stock ? offer.stock.replaceAll("_", " ") : (offer.currency !== "INR" ? offer.currency : offer.condition);
    return `<tr><td>${escapeHtml(offer.retailer)}</td><td>${escapeHtml(why)}</td><td class="right">${escapeHtml(money(offer) || "—")}</td></tr>`;
  }).join("");
  return `<div class="excluded"><h3>Not counted as the cheapest in-stock offer</h3><table><thead><tr><th>Retailer</th><th>Why</th><th class="right">Price</th></tr></thead><tbody>${rows}</tbody></table></div>`;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  errorBox.hidden = true;
  go.disabled = true;
  go.textContent = "Checking offers…";
  try {
    const response = await fetch("/api/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query: queryInput.value,
        location: locationInput.value,
        include_used: includeUsed.checked,
        sample: forceSample.checked || !keyPresent,
      }),
    });
    const data = await response.json();
    if (!response.ok || !data.ok) {
      results.hidden = true;
      banner.hidden = true;
      errorBox.hidden = false;
      errorBox.textContent = data.error || "Search failed.";
      return;
    }
    render(data);
  } catch (err) {
    results.hidden = true;
    errorBox.hidden = false;
    errorBox.textContent = "The local server did not respond.";
  } finally {
    go.disabled = false;
    go.textContent = "Find the cheapest in stock";
  }
});

loadStatus().catch(() => {
  note.textContent = "Could not read server status.";
});
