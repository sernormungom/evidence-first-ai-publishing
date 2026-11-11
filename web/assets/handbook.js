/* One language index is shared by the header and homepage search controls. */
const indexes = new Map();

function loadIndex(url) {
  if (!indexes.has(url)) {
    indexes.set(url, fetch(url).then(response => {
      if (!response.ok) throw new Error('Search index unavailable');
      return response.json();
    }).catch(error => {
      indexes.delete(url); // A later search can retry after a temporary failure.
      throw error;
    }));
  }
  return indexes.get(url);
}

function score(hay, terms) {
  hay = hay.toLowerCase();
  let total = 0;
  for (const term of terms) {
    if (hay.includes(term)) total += term.length > 3 ? 2 : 1;
  }
  return total;
}

document.querySelectorAll('.searchbox').forEach(search => {
  const box = search.querySelector('input');
  const results = search.querySelector('.search-results');
  const status = search.querySelector('.search-status');
  const indexUrl = new URL(search.dataset.index, document.baseURI);
  let request = 0;

  function close() {
    request += 1;
    results.hidden = true;
    status.textContent = '';
  }

  function message(text) {
    const paragraph = document.createElement('p');
    paragraph.className = 'search-message';
    paragraph.textContent = text;
    results.replaceChildren(paragraph);
    results.hidden = false;
    status.textContent = text;
  }

  async function update() {
    const current = ++request;
    const terms = box.value.toLowerCase().split(/\s+/).filter(Boolean);
    results.replaceChildren();
    results.hidden = true;
    status.textContent = '';
    if (!terms.length) return;

    try {
      const index = await loadIndex(indexUrl.href);
      if (current !== request) return;
      const hits = [];
      for (const article of index) {
        for (const question of article.questions) {
          const weight = score(question, terms) * 2 + score(article.title, terms);
          if (weight > 0) hits.push({ weight, question, article });
        }
        const weight = score(article.title + ' ' + article.excerpt, terms);
        if (weight > 0 && !article.questions.length) {
          hits.push({ weight, question: article.title, article });
        }
      }
      hits.sort((a, b) => b.weight - a.weight);
      const selected = hits.slice(0, 8);
      if (!selected.length) {
        message(search.dataset.empty);
        return;
      }
      for (const hit of selected) {
        const link = document.createElement('a');
        link.href = new URL(hit.article.url, indexUrl).href;
        const title = document.createElement('span');
        title.className = 'q';
        title.textContent = hit.question;
        const context = document.createElement('span');
        context.className = 'in';
        context.textContent = `${hit.article.folder} · ${hit.article.title}`;
        link.append(title, context);
        results.append(link);
      }
      results.hidden = false;
      status.textContent = search.dataset.count.replace('{count}', selected.length);
    } catch {
      if (current === request) message(search.dataset.error);
    }
  }

  box.addEventListener('input', update);
  box.addEventListener('focus', update);
  search.addEventListener('keydown', event => {
    if (event.key === 'Escape') {
      box.focus();
      close();
    }
    if (event.key === 'ArrowDown' && event.target === box && !results.hidden) {
      const first = results.querySelector('a');
      if (first) {
        event.preventDefault();
        first.focus();
      }
    }
  });
  search.addEventListener('focusout', event => {
    if (!search.contains(event.relatedTarget)) close();
  });
  document.addEventListener('click', event => {
    if (!search.contains(event.target)) close();
  });
});

// Keep the desktop tree visible and use a native disclosure on smaller screens.
const menu = document.querySelector('.topic-menu');
if (menu) {
  const desktop = window.matchMedia('(min-width: 1024px)');
  const syncMenu = () => { menu.open = desktop.matches; };
  syncMenu();
  desktop.addEventListener('change', syncMenu);
}
