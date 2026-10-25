'use strict';

// jsdom tests for the Step Harness app in index.html.
// The API is replaced with a stub, no network is touched.
// Run with: npm test

const fs = require('fs');
const path = require('path');
const assert = require('assert');
const { JSDOM } = require('jsdom');

const html = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

// fetch stub: handler(callIndex, call) returns either a response shape
// { ok, status, json } or an Error instance to simulate a network failure
function makeFetch(handler) {
  const calls = [];
  const f = async (url, opts = {}) => {
    const call = { url, headers: opts.headers || {}, body: opts.body ? JSON.parse(opts.body) : null };
    calls.push(call);
    const res = handler(calls.length - 1, call);
    if (res instanceof Error) throw res;
    return { ok: res.ok !== false, status: res.status || 200, json: async () => res.json };
  };
  return { f, calls };
}

// OpenAI-shaped reply carrying `obj` as the assistant message content
const ai = (obj) => ({
  json: { choices: [{ message: { content: JSON.stringify(obj) } }] },
});

const SPLIT = ai({
  steps: [
    { action: 'Открыть письмо в черновиках', verification: 'письмо открыто', secs: 30 },
    { action: 'Прочитать письмо до конца', verification: 'дочитан до конца', secs: 60 },
  ],
});
const SUB1 = ai({
  steps: [
    { action: 'Открыть папку черновики', verification: 'папка открыта', secs: 30 },
    { action: 'Кликнуть по первому письму', verification: 'письмо на экране', secs: 20 },
  ],
  lesson: {
    when: 'длинный черновик письма',
    if: 'завис на первом шаге дольше 4 минут',
    do: 'просить только три пункта строчными буквами',
    check: 'написал больше 15 слов за минуту',
  },
});
const SUB2 = ai({
  steps: [{ action: 'Прочитать тему письма вслух', verification: 'тема произнесена', secs: 20 }],
  lesson: {
    when: 'длинный черновик письма',
    if: 'смотрит в пустой экран',
    do: 'просить только три пункта без оформления',
    check: 'первый пункт написан',
  },
});

function boot(handler, seed = {}) {
  const stub = makeFetch(handler);
  const alerts = [];
  const dom = new JSDOM(html, {
    url: 'https://localhost/',
    runScripts: 'dangerously',
    pretendToBeVisual: true,
    beforeParse(w) {
      w.fetch = stub.f;
      w.alert = (m) => alerts.push(m);
      if (!w.matchMedia) w.matchMedia = () => ({ matches: false });
      const items = Object.assign({ k: 'test-key' }, seed);
      for (const [key, value] of Object.entries(items)) w.localStorage.setItem(key, String(value));
    },
  });
  return { dom, w: dom.window, d: dom.window.document, stub, alerts };
}

const start = (t, goal) => {
  t.d.getElementById('goal').value = goal;
  t.d.getElementById('b-go').click();
};

const tests = [];
const test = (name, fn) => tests.push([name, fn]);

test('splits a goal into steps and shows exactly one', async () => {
  const t = boot(() =>
    ai({
      steps: [
        { action: 'Открыть файл plan.md', verification: 'файл открыт на экране', secs: 30 },
        { action: 'Прочитать первый абзац', verification: 'абзац прочитан', secs: 60 },
        { action: 'Выписать одну мысль', verification: 'одна строка написана', secs: 90 },
      ],
    })
  );
  try {
    start(t, 'Разобрать завал в заметках');
    await wait(30);
    assert.ok(t.d.getElementById('s-in').hidden, 'input view hidden');
    assert.ok(!t.d.getElementById('s-run').hidden, 'run view visible');
    assert.strictEqual(t.d.getElementById('cnt').textContent, '1 из 3');
    assert.strictEqual(t.d.getElementById('title').textContent, 'Открыть файл plan.md');
    assert.strictEqual(t.d.getElementById('chk').textContent, 'Готово, когда: файл открыт на экране');
    assert.strictEqual(t.d.getElementById('bar').children.length, 3);
    assert.strictEqual(t.stub.calls.length, 1);
    assert.strictEqual(t.stub.calls[0].url, 'https://api.openai.com/v1/chat/completions');
    assert.strictEqual(t.stub.calls[0].headers.Authorization, 'Bearer test-key');
    assert.strictEqual(t.stub.calls[0].body.messages[0].role, 'system');
    assert.strictEqual(t.stub.calls[0].body.messages[1].content, 'Разобрать завал в заметках');
  } finally {
    t.dom.window.close();
  }
});

test('done button advances steps and finishes the session', async () => {
  const t = boot(() =>
    ai({
      steps: [
        { action: 'Взять ручку', verification: 'ручка в руке', secs: 15 },
        { action: 'Написать одно слово', verification: 'слово на бумаге', secs: 30 },
      ],
    })
  );
  try {
    start(t, 'Начать список дел');
    await wait(30);
    t.d.getElementById('b-ok').click();
    await wait(10);
    assert.strictEqual(t.d.getElementById('cnt').textContent, '2 из 2');
    assert.strictEqual(t.d.getElementById('title').textContent, 'Написать одно слово');
    t.d.getElementById('b-ok').click();
    await wait(10);
    assert.ok(!t.d.getElementById('s-done').hidden, 'done view visible');
    assert.match(t.d.getElementById('sum').textContent, /Шагов: 2/);
    assert.strictEqual(t.w.localStorage.getItem('st'), null, 'session cleared after finish');
  } finally {
    t.dom.window.close();
  }
});

test('stuck button cuts the step into substeps and records a candidate (n=1)', async () => {
  const t = boot((i) => [SPLIT, SUB1][i]);
  try {
    start(t, 'Ответить на письмо шефу');
    await wait(30);
    t.d.getElementById('b-st').click();
    await wait(30);
    // 2 steps - 1 current + 2 substeps = 3
    assert.strictEqual(t.d.getElementById('cnt').textContent, '1 из 3');
    assert.strictEqual(t.d.getElementById('title').textContent, 'Открыть папку черновики');
    assert.strictEqual(t.d.getElementById('bar').children.length, 3);
    // the stuck request carries the exact step the person froze on
    assert.ok(t.stub.calls[1].body.messages[1].content.includes('Открыть письмо в черновиках'));
    // first lapse is only a candidate
    const les = JSON.parse(t.w.localStorage.getItem('les'));
    assert.strictEqual(les.length, 1);
    assert.strictEqual(les[0].n, 1);
    assert.strictEqual(les[0].when, 'длинный черновик письма');
    assert.match(t.d.getElementById('lbox').textContent, /Правила: 0, кандидаты: 1/);
  } finally {
    t.dom.window.close();
  }
});

test('a repeated similar lapse makes the rule active (n=2)', async () => {
  const t = boot((i) => [SPLIT, SUB1, SUB2][i]);
  try {
    start(t, 'Ответить на письмо шефу');
    await wait(30);
    t.d.getElementById('b-st').click(); // lapse 1 -> candidate
    await wait(30);
    t.d.getElementById('b-ok').click(); // finish the first substep
    await wait(10);
    t.d.getElementById('b-st').click(); // lapse 2 on the next substep
    await wait(30);
    const les = JSON.parse(t.w.localStorage.getItem('les'));
    assert.strictEqual(les.length, 1, 'similar lapses merge into one record');
    assert.strictEqual(les[0].n, 2, 'counter grew to 2');
    assert.match(t.d.getElementById('lbox').textContent, /Правила: 1, кандидаты: 0/);
  } finally {
    t.dom.window.close();
  }
});

test('an active rule lands in the next split prompt, a candidate does not', async () => {
  const rule = {
    when: 'длинный черновик письма',
    if: 'завис на первом шаге дольше 4 минут',
    do: 'просить только три пункта строчными буквами',
    check: 'написал больше 15 слов за минуту',
    n: 1,
    t: Date.now(),
  };
  const t1 = boot(() => SPLIT, { les: JSON.stringify([rule]) });
  try {
    start(t1, 'Разобрать длинный черновик письма');
    await wait(30);
    assert.ok(t1.stub.calls[0].body.messages[0].content.includes('none yet'), 'candidate must stay out of the prompt');
  } finally {
    t1.dom.window.close();
  }
  const t2 = boot(() => SPLIT, { les: JSON.stringify([{ ...rule, n: 2 }]) });
  try {
    start(t2, 'Разобрать длинный черновик письма');
    await wait(30);
    const sys = t2.stub.calls[0].body.messages[0].content;
    assert.ok(sys.includes('WHEN длинный черновик письма'), 'rule present as WHEN');
    assert.ok(sys.includes('IF завис на первом шаге дольше 4 минут'), 'signal present as IF');
    assert.ok(sys.includes('DO просить только три пункта строчными буквами'), 'action present as DO');
  } finally {
    t2.dom.window.close();
  }
});

test('session survives a page reload', async () => {
  const a = boot(() =>
    ai({
      steps: [
        { action: 'Шаг один', verification: 'первое сделано', secs: 30 },
        { action: 'Шаг два', verification: 'второе сделано', secs: 30 },
        { action: 'Шаг три', verification: 'третье сделано', secs: 30 },
      ],
    })
  );
  start(a, 'Пройти три шага');
  await wait(30);
  a.d.getElementById('b-ok').click();
  await wait(10);
  const dump = {};
  for (let i = 0; i < a.w.localStorage.length; i++) {
    const key = a.w.localStorage.key(i);
    dump[key] = a.w.localStorage.getItem(key);
  }
  assert.ok(dump.st, 'progress was persisted');
  a.dom.window.close();

  const b = boot(() => {
    throw new Error('no API call expected after reload');
  }, dump);
  try {
    await wait(30);
    assert.ok(!b.d.getElementById('s-run').hidden, 'run view restored');
    assert.strictEqual(b.d.getElementById('cnt').textContent, '2 из 3');
    assert.strictEqual(b.d.getElementById('title').textContent, 'Шаг два');
    assert.strictEqual(b.stub.calls.length, 0);
  } finally {
    b.dom.window.close();
  }
});

test('API error surfaces as a quiet toast, not an alert', async () => {
  const t = boot(() => ({
    ok: false,
    status: 401,
    json: { error: { message: 'Incorrect API key provided' } },
  }));
  try {
    start(t, 'Что-нибудь');
    await wait(30);
    assert.ok(!t.d.getElementById('s-in').hidden, 'input view still visible');
    assert.strictEqual(t.d.getElementById('toast').textContent, 'Incorrect API key provided');
    assert.ok(t.d.getElementById('toast').classList.contains('on'), 'toast is shown');
    assert.strictEqual(t.alerts.length, 0, 'no alert() anywhere');
  } finally {
    t.dom.window.close();
  }
});

test('stuck without network still gives a fallback step', async () => {
  const t = boot((i) => (i === 0 ? SPLIT : new TypeError('Failed to fetch')));
  try {
    start(t, 'Ответить на письмо шефу');
    await wait(30);
    t.d.getElementById('b-st').click();
    await wait(30);
    assert.strictEqual(
      t.d.getElementById('title').textContent,
      'Открой нужный файл или окно и больше ничего не делай'
    );
    assert.strictEqual(t.d.getElementById('chk').textContent, 'Готово, когда: окно открыто');
    assert.match(t.d.getElementById('toast').textContent, /Failed to fetch/);
    assert.strictEqual(t.d.getElementById('cnt').textContent, '1 из 2');
  } finally {
    t.dom.window.close();
  }
});

test('HTML from rules and steps is never parsed as markup', async () => {
  const rule = {
    when: '<img src=x onerror=alert(1)> черновик',
    if: '',
    do: 'просить <b>короткие пункты</b>',
    check: '',
    n: 2,
    t: Date.now(),
  };
  const splitHtml = ai({
    steps: [{ action: '<b>Открыть</b> файл <img src=x>', verification: 'файл открыт', secs: 30 }],
  });
  const t = boot(() => splitHtml, { les: JSON.stringify([rule]) });
  try {
    const box = t.d.getElementById('lbox');
    assert.ok(box.textContent.includes('<img src=x onerror=alert(1)> черновик'), 'rule shown as text');
    assert.strictEqual(t.d.querySelectorAll('#lbox img').length, 0, 'no img element created');
    // the rule line is the last div; the app's own <b> header may exist, the rule text may not
    const line = box.lastElementChild;
    assert.strictEqual(line.tagName, 'DIV');
    assert.ok(line.textContent.includes('просить <b>короткие пункты</b>'), 'tags kept literally');
    assert.strictEqual(line.children.length, 0, 'rule text produced no elements');
    start(t, 'Разобрать заметки');
    await wait(30);
    assert.strictEqual(t.d.getElementById('title').textContent, '<b>Открыть</b> файл <img src=x>');
    assert.strictEqual(t.d.querySelectorAll('#title b, #title img').length, 0, 'step title is text only');
    assert.strictEqual(t.alerts.length, 0, 'the injected onerror never ran');
  } finally {
    t.dom.window.close();
  }
});

(async () => {
  let failed = 0;
  for (const [name, fn] of tests) {
    try {
      await fn();
      console.log('ok   ' + name);
    } catch (e) {
      failed++;
      console.log('FAIL ' + name);
      console.log('     ' + (e && e.message));
    }
  }
  console.log(failed ? `\n${failed} of ${tests.length} tests failed` : `\nall ${tests.length} tests passed`);
  process.exit(failed ? 1 : 0);
})();
