const form = document.querySelector('#search-form');
const queryInput = document.querySelector('#query');
const engineInput = document.querySelector('#engine');
const maxResultsInput = document.querySelector('#max-results');
const hidePromotedInput = document.querySelector('#hide-promoted');
const sourceTypesInput = document.querySelector('#source-types');
const statusBox = document.querySelector('#status');
const resultsBox = document.querySelector('#results');
const resultTemplate = document.querySelector('#result-template');
const apiLink = document.querySelector('#api-link');

function setStatus(message, mode = 'info') {
  statusBox.textContent = message;
  statusBox.dataset.mode = mode;
}

function truncate(text, length = 320) {
  if (!text) return 'No preview text was available for this result.';
  return text.length > length ? `${text.slice(0, length).trim()}…` : text;
}

function hostnameFromUrl(url) {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return url;
  }
}

function updateApiLink() {
  const q = queryInput.value.trim() || 'fastapi';
  const params = new URLSearchParams({
    q,
    max_results: maxResultsInput.value,
    engine: engineInput.value,
    hide_promoted: hidePromotedInput.value,
    source_types: sourceTypesInput.value,
  });
  apiLink.href = `/api/search?${params.toString()}`;
}

function renderResults(results) {
  resultsBox.replaceChildren();

  if (!results.length) {
    const empty = document.createElement('p');
    empty.className = 'empty-state';
    empty.textContent = 'No results found. Try a different search phrase or another engine.';
    resultsBox.append(empty);
    return;
  }

  for (const result of results) {
    const card = resultTemplate.content.cloneNode(true);
    const link = card.querySelector('.title');
    const source = card.querySelector('.source');
    const url = card.querySelector('.url');
    const snippet = card.querySelector('.snippet');
    const imageStrip = card.querySelector('.image-strip');
    const favicon = card.querySelector('.favicon');
    const anonymousView = card.querySelector('.anonymous-view');
    const host = result.source_name || hostnameFromUrl(result.url);

    link.href = result.url;
    link.textContent = result.title || result.url;
    source.textContent = host;
    url.textContent = result.url;
    snippet.textContent = truncate(result.content);
    favicon.textContent = host.slice(0, 1).toUpperCase();
    anonymousView.href = result.anonymous_url || `/api/anonymous?url=${encodeURIComponent(result.url)}`;

    for (const imageUrl of (result.images || []).slice(0, 3)) {
      const image = document.createElement('img');
      image.src = imageUrl;
      image.alt = '';
      image.loading = 'lazy';
      image.referrerPolicy = 'no-referrer';
      imageStrip.append(image);
    }

    if (!imageStrip.children.length) {
      imageStrip.remove();
    }

    resultsBox.append(card);
  }
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const q = queryInput.value.trim();

  if (!q) {
    setStatus('Please enter a search query.', 'error');
    queryInput.focus();
    return;
  }

  updateApiLink();
  setStatus(`Searching for “${q}”…`, 'loading');
  resultsBox.replaceChildren();

  try {
    const response = await fetch(apiLink.href, { headers: { Accept: 'application/json' } });
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || `Request failed with ${response.status}`);
    }
    const payload = await response.json();
    renderResults(payload.results || []);
    setStatus(
      `Found ${payload.count} result${payload.count === 1 ? '' : 's'} for “${payload.query}”.`,
      'success',
    );
  } catch (error) {
    setStatus(error.message || 'Search failed. Please try again.', 'error');
  }
});

for (const field of [queryInput]) {
  field.addEventListener('input', updateApiLink);
  field.addEventListener('change', updateApiLink);
}

updateApiLink();
