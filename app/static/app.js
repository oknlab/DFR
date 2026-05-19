const form = document.querySelector('#search-form');
const queryInput = document.querySelector('#query');
const maxResultsInput = document.querySelector('#max-results');
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

function renderResults(results) {
  resultsBox.replaceChildren();

  if (!results.length) {
    const empty = document.createElement('p');
    empty.className = 'empty-state';
    empty.textContent = 'No results found. Try a different search phrase.';
    resultsBox.append(empty);
    return;
  }

  for (const result of results) {
    const card = resultTemplate.content.cloneNode(true);
    const link = card.querySelector('.title');
    const source = card.querySelector('.source');
    const snippet = card.querySelector('.snippet');
    const imageStrip = card.querySelector('.image-strip');

    link.href = result.url;
    link.textContent = result.title || result.url;
    source.textContent = result.source_name || new URL(result.url).hostname;
    snippet.textContent = truncate(result.content);

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
  const maxResults = maxResultsInput.value;

  if (!q) {
    setStatus('Please enter a search query.', 'error');
    queryInput.focus();
    return;
  }

  const params = new URLSearchParams({ q, max_results: maxResults });
  const apiUrl = `/api/search?${params.toString()}`;
  apiLink.href = apiUrl;
  setStatus(`Searching for “${q}”…`, 'loading');
  resultsBox.replaceChildren();

  try {
    const response = await fetch(apiUrl, { headers: { Accept: 'application/json' } });
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || `Request failed with ${response.status}`);
    }
    const payload = await response.json();
    renderResults(payload.results || []);
    setStatus(`Found ${payload.count} result${payload.count === 1 ? '' : 's'} for “${payload.query}”.`, 'success');
  } catch (error) {
    setStatus(error.message || 'Search failed. Please try again.', 'error');
  }
});
