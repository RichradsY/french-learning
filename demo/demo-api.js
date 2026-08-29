(() => {
  const nativeFetch = window.fetch.bind(window);
  const dataPromise = nativeFetch('demo-data.json', {cache: 'no-store'})
    .then(response => {
      if (!response.ok) throw new Error('Demo data is unavailable');
      return response.json();
    })
    .then(prepareDemoData);

  function clone(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function localDate(year, month, day) {
    return `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
  }

  function prepareDemoData(source) {
    const data = clone(source);
    const now = new Date();
    const year = now.getFullYear();
    const month = now.getMonth() + 1;
    const today = localDate(year, month, now.getDate());
    const vocabularyDates = [...new Set(data.vocabulary.map(item => item.study_date))].sort();
    const vocabularyDateMap = new Map(vocabularyDates.map((value, index) => [
      value,
      localDate(year, month, Math.min(index + 1, 28)),
    ]));

    data.daily.study_date = today;
    data.reading.study_date = today;
    data.writing.study_date = today;
    data.vocabulary.forEach(item => {
      item.study_date = vocabularyDateMap.get(item.study_date);
    });
    data.history.forEach(item => {
      item.study_date = today;
    });
    data.mistakes.forEach(item => {
      item.study_date = today;
    });
    return data;
  }

  function jsonResponse(payload, status = 200) {
    return new Response(JSON.stringify(payload), {
      status,
      headers: {'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store'},
    });
  }

  function route(path, method, body, data) {
    if (method === 'GET' && path === '/api/today') return data.daily;
    if (method === 'GET' && /^\/api\/sessions\/\d+$/.test(path)) return data.daily;
    if (method === 'GET' && path === '/api/tasks/reading') return data.reading;
    if (method === 'GET' && path === '/api/tasks/writing') return data.writing;
    if (method === 'GET' && /^\/api\/tasks\/\d+$/.test(path)) {
      return Number(path.split('/').pop()) === data.reading.id ? data.reading : data.writing;
    }
    if (method === 'GET' && path === '/api/history') return data.history;
    if (method === 'GET' && path === '/api/mistakes') return data.mistakes;
    if (method === 'GET' && path === '/api/grammar') return data.grammar;
    if (method === 'GET' && path === '/api/conjugations') return data.conjugations;
    if (method === 'GET' && path === '/api/vocabulary') return data.vocabulary;
    const starMatch = path.match(/^\/api\/vocabulary\/(\d+)\/star$/);
    if (method === 'POST' && starMatch) {
      const item = data.vocabulary.find(word => word.id === Number(starMatch[1]));
      if (!item) return {error: {message: 'Mot introuvable'}};
      item.starred = Boolean(body.starred);
      return item;
    }
    return {error: {message: 'Cette action est désactivée dans la démonstration.'}};
  }

  window.fetch = async (input, options = {}) => {
    const url = new URL(typeof input === 'string' ? input : input.url, window.location.href);
    if (!url.pathname.includes('/api/')) return nativeFetch(input, options);
    const apiPath = url.pathname.slice(url.pathname.indexOf('/api/'));
    const method = String(options.method || 'GET').toUpperCase();
    let body = {};
    try {
      body = options.body ? JSON.parse(options.body) : {};
    } catch (_error) {
      return jsonResponse({error: {message: 'Requête de démonstration invalide'}}, 400);
    }
    const data = await dataPromise;
    const payload = route(apiPath, method, body, data);
    const status = payload?.error ? 405 : 200;
    return jsonResponse(clone(payload), status);
  };
})();
