# Step Harness: исполнительный помощник для людей с СДВГ

Спецификация v2. Клиентское приложение в одном HTML-файле, ключи пользователя (BYOK), пошаговый режим "одно действие на экране", память на правилах, которые копятся из срывов самого человека.

---

## 1. Что это и чем отличается

Проблема знакомая: большая размытая задача, запуск не происходит, список из десяти пунктов только пугает. Обычные таск-менеджеры требуют, чтобы человек сам себя организовал, а с этим как раз сложности.

Step Harness делает три вещи.

1. Режет цель на шаги по одной-трём минутам и показывает ровно один шаг. Первый шаг почти бесплатный: открыть файл, взять ручку.
2. Держит рядом таймер с целевым временем шага, потому что время обычно уплывает незаметно.
3. Запоминает, где человек ломается. Нажал "Застрял", и шаг режется на подшаги, а из срыва получается правило вида WHEN / IF / DO / CHECK. Если похожий срыв повторился, правило становится рабочим и попадает в следующие разбивки.

Третий пункт и есть отличие. Goblin.tools и подобные разбивают задачи одинаково для всех, Tiimo и Finch упор делают на визуальное планирование и геймификацию. Персональной памяти про то, на чём ломаешься именно ты, в них, насколько я знаю, нет. Это я по памяти, сравнительный обзор не делал, перед питчем стоит проверить.

Что это не такое: не лечение, не терапия, не замена специалисту. В интерфейсе и в README это должно быть написано прямо. Формулировки про "дофаминовое сопротивление" и подобное из первой версии убраны: это красивые слова, за которыми у нас нет проверенных данных.

---

## 2. Проверка зависимостей из первой версии

Я прошёл по каждому репозиторию поиском. Часть из них существует, часть найти не удалось, и в спеке они теперь не упоминаются как основа.

| Что было в спеке | Что нашлось | Решение |
|---|---|---|
| noahshinn/reflexion | Существует. Код к статье NeurIPS 2023 (HotPotQA, AlfWorld, HumanEval). Исследовательский код, не библиотека | Берём идею: текстовая саморефлексия подаётся в следующую попытку |
| jerrywang121/ilearned | Не нашёл | Формат WHEN / IF / DO / CHECK остаётся как наш собственный, без ссылок на источник |
| rohansx/reflect (Reflect MCP) | Не нашёл. У rohansx другие репозитории (homn, wardn, workz) | Убрано. Реальный аналог по идее: SuperMemory MCP (pip supermemory-agent-mcp), цикл retrieve, record_failure, reflect, validate, process_promotions. Проект молодой (v0.2.x), на Python, в браузер напрямую не встроишь |
| rennzhang/oh-my-experience | Не нашёл. rennzhang это фронтенд-разработчик с другими репозиториями | Убрано |
| BITHLP/LifeMem | Под BITHLP такого нет. LifeMem это статья arXiv 2608.19621 про социальную симуляцию LLM-агентов, код у halsayxi/LifeMem | Не подходит как "кластеризация эвристик". Убрано |
| madebymustafa/design-taste | Под таким автором не нашёл | Убрано |
| taste-skill, industrial-brutalist-ui | Существует: Leonxlnx/taste-skill, скилл в статусе beta | Оставлено как опция для разработки интерфейса |
| ui-ux-pro-max-skill | Существует: nextlevelbuilder/ui-ux-pro-max-skill, MIT, каталог стилей и палитр | Оставлено как опция |
| Mendiak/less-is-more-ui | Есть на skills.sh, маленький (единицы звёзд) | Оставлено как опция, подходит по духу |
| scottstts/Threejs-Awesome-Graphics-Agent-Skills | Существует, 24 скилла про сложную графику (облака, океан, пост-обработка) | Для шести узлов избыточно, не берём |
| CloudAI-X/threejs-skills | Существует, базовые темы Three.js | Достаточно для нашей сцены |
| openapi-validation, api-schema-analyzer | Не проверял | Убрано: своего API у приложения нет |
| Scrolltide | Не проверял | Убрано. Mobbin, Fontshare и Coolors я знаю как существующие сервисы, но их тоже не проверял |
| @xenova/transformers | Насколько знаю, пакет переехал в @huggingface/transformers. Проверь перед использованием | Фаза 3, под вопросом |

Скиллы для агентов, которые перечислены выше (taste-skill, ui-ux-pro-max и другие), это инструменты на этапе разработки интерфейса, а не часть приложения. Скилл это исполняемая инструкция для агента, поэтому перед установкой стоит прочитать его SKILL.md. В README одного из Three.js-репозиториев команда клонирования указывает на другой репозиторий, так что ставить лучше через npx-установщик или копированием папки, а не вслепую.

---

## 3. Что взято из i-have-adhd и learnharness

**i-have-adhd** (ayghri, лицензия MIT, около 58 тысяч звёзд). Это скилл для Claude Code, который меняет стиль ответов агента. Сам скилл в приложение не ставится, но его десять правил почти один в один подходят к тому, как должна писать наша модель. Их можно использовать с указанием источника (MIT это разрешает). Вот как они ложатся на приложение:

1. Сначала действие: в промпте разбивки глагол первым.
2. Нумерация шагов: степпер.
3. Один следующий шаг в конце: поле "Готово, когда".
4. Без отступлений и 10. без вступлений: в промпте запрещены похвала и вода.
5. Время оценивать конкретно, в минутах и секундах: у каждого шага поле secs и таймер.
6. Победы должны быть видны: короткая награда за каждый шаг, а не только в конце.
7. Ошибки сообщать буднично: кнопка "Застрял" без чувства вины, ответ без нравоучений.
8. Списки не длиннее пяти: шагов в разбивке три-шесть, правил в промпте не больше пяти.

**learnharness** (amosblomqvist, AGPL-3.0, мало звёзд). Это про обучение, не про выполнение задач. Идея, которую стоит перенять позже: перед уроком измерить, что человек уже знает, и учить по одному шагу. Код копировать не надо: AGPL заразная, и тебе пришлось бы открывать исходники всего, что к нему прикоснулось. Идея не защищена, реализация да.

---

## 4. Как устроена память

Цикл такой.

```
цель -> выбор правил по теме -> модель режет на шаги -> человек идёт по шагам
                                                              |
                                                        "Застрял"
                                                              |
                           подшаги вместо текущего <- модель режет шаг и пишет кандидата в правила
                                                              |
                                      похожий кандидат уже есть? да -> счётчик +1, правило становится рабочим
```

**Формат правила:**

```json
{
  "when": "длинный черновик письма",
  "if": "человек завис на первом шаге дольше 4 минут",
  "do": "просить только три пункта строчными буквами, без оформления",
  "check": "написал ли он больше 15 слов за минуту",
  "n": 2,
  "t": 1792965180000
}
```

**Правило повышения.** Один срыв ничего не доказывает, это может быть плохой день. Поэтому новый урок сначала кандидат (n = 1). Когда приходит похожий (пересечение слов выше 0,6), счётчик растёт, и при n >= 2 это уже рабочее правило. В промпт попадают только рабочие.

**Отбор.** Вливать все правила в каждый промпт нельзя: через месяц он раздуется. Сейчас выбираются до пяти правил с наибольшим пересечением слов с целью. Если ничего не пересекается, берутся два самых свежих. Лимит хранилища 60 записей, при переполнении первыми уходят кандидаты. В фазе 3 пересечение слов можно заменить эмбеддингами.

---

## 5. Интерфейс

Принципы:

- Один шаг на экране, крупно. Остальное только полоской прогресса.
- Мгновенная награда за каждый шаг: короткий звук и подсветка карточки. Звук можно выключить.
- Таймер идёт вверх и показывает целевое время шага. Когда лимит превышен, цифры становятся оранжевыми. Никаких всплывающих окон.
- Тихие уведомления вместо alert(). Человеку, который завис, модальное окно только мешает.
- Сенсорный фон опционален и по умолчанию выключен. Вариантов три: выкл, коричневый шум (генерируется в браузере), видео по ссылке пользователя. Захардкоженных плейлистов нет. Данных, что видео помогает, у меня нет, а оно занимает внимание, поэтому решает человек. Видео грузится с youtube-nocookie.
- 3D-граф тоже опция и по умолчанию выключен, он подгружает Three.js только после включения. На шести узлах он красив, но польза у него ровно та же, что у полоски прогресса.
- Уважается prefers-reduced-motion: анимации отключаются.
- Диктовка цели через Web Speech API, где браузер её поддерживает. Печатать длинную формулировку уже порог.
- Прогресс переживает перезагрузку страницы.

Палитра и стиль прежние: тёмный фон `#0c0d10`, карточки `#14171f`, акцент `#22c55e`.

---

## 6. MVP: один файл index.html

Сохрани как `index.html` и открой в браузере. Сборки и бэкенда нет. Работает с OpenAI, Anthropic (напрямую из браузера, с заголовком `anthropic-dangerous-direct-browser-access`) и OpenRouter. Название модели в настройках можно менять.

```html
<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Step Harness</title>
<style>
:root{--bg:#0c0d10;--card:#14171f;--line:#1f2430;--ac:#22c55e;--ac2:#4ade80;--warn:#f59e0b;--bad:#ef4444;--tx:#f3f4f6;--sub:#9ca3af}
*{box-sizing:border-box;margin:0;padding:0}
[hidden]{display:none!important}
body{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;background:var(--bg);color:var(--tx);min-height:100vh;display:flex;justify-content:center;padding:20px}
main{width:100%;max-width:560px;display:flex;flex-direction:column;gap:16px}
details,.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px}
.col{display:flex;flex-direction:column;gap:12px}
summary{cursor:pointer;font-size:12px;color:var(--sub);text-transform:uppercase;letter-spacing:.06em}
.row{display:flex;gap:8px;margin-top:10px;flex-wrap:wrap;align-items:center}
input,select,textarea{background:var(--bg);border:1px solid var(--line);color:var(--tx);border-radius:6px;padding:8px 10px;font-size:14px;font-family:inherit}
input[type=text],input[type=password]{flex:1;min-width:140px}
textarea{width:100%;height:110px;resize:none;font-size:16px}
textarea:focus,input:focus{outline:2px solid var(--ac)}
label{font-size:12px;color:var(--sub);display:flex;gap:6px;align-items:center}
button{font:inherit;font-weight:700;font-size:14px;border:0;border-radius:8px;padding:14px 18px;cursor:pointer;background:var(--line);color:var(--tx)}
button:focus-visible{outline:2px solid var(--ac2);outline-offset:2px}
button:disabled{opacity:.5;cursor:wait}
.go{background:var(--ac);color:#000}
.stuck{background:transparent;border:1px solid var(--bad);color:var(--bad)}
.small{padding:6px 10px;font-size:12px}
h1{font-size:22px}
.sub{font-size:13px;color:var(--sub);line-height:1.5}
#bar{display:flex;gap:4px}
#bar i{flex:1;height:6px;border-radius:3px;background:var(--line);transition:background .2s}
#bar i.d{background:var(--ac)}
#bar i.c{background:var(--tx)}
.flash{animation:fl .35s}
@keyframes fl{from{box-shadow:0 0 0 3px var(--ac2)}to{box-shadow:0 0 0 0 transparent}}
#title{font-size:24px;font-weight:700;line-height:1.35}
#chk{font-size:14px;color:var(--sub);border-left:3px solid var(--ac);padding-left:10px}
#tm{font-variant-numeric:tabular-nums;font-size:14px;color:var(--sub)}
#tm.over{color:var(--warn)}
#cv{width:100%;height:120px;border-radius:8px;background:#0c0d13;border:1px solid var(--line);display:none}
#anc iframe{width:100%;aspect-ratio:16/9;border:0;border-radius:8px;margin-top:10px}
#toast{position:fixed;bottom:20px;left:50%;transform:translateX(-50%);background:var(--card);border:1px solid var(--line);padding:10px 16px;border-radius:8px;font-size:13px;opacity:0;transition:opacity .2s;pointer-events:none;max-width:90vw}
#toast.on{opacity:1}
.lbox{font-size:12px;color:var(--sub);line-height:1.5}
.lbox b{color:var(--tx)}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
</style>
</head>
<body>
<main>
  <details id="set">
    <summary>Настройки</summary>
    <div class="row">
      <select id="prov">
        <option value="openai">OpenAI</option>
        <option value="anthropic">Anthropic</option>
        <option value="openrouter">OpenRouter</option>
      </select>
      <input type="text" id="model" placeholder="модель">
    </div>
    <div class="row">
      <input type="password" id="key" placeholder="API-ключ" autocomplete="off">
      <label><input type="checkbox" id="rem"> помнить ключ</label>
    </div>
    <div class="row">
      <label><input type="checkbox" id="snd" checked> звук</label>
      <label><input type="checkbox" id="c3"> 3D-граф</label>
      <select id="ancsel">
        <option value="off">фон: выкл</option>
        <option value="noise">фон: шум</option>
        <option value="video">фон: видео</option>
      </select>
    </div>
    <div id="anc"></div>
    <p class="sub" style="margin-top:10px">Ключ хранится в браузере открытым текстом. Цели уходят выбранному провайдеру. Это не медицинский инструмент.</p>
  </details>

  <section id="s-in" class="card col">
    <h1>Что висит над головой?</h1>
    <textarea id="goal" placeholder="Любая цель, хоть расплывчатая"></textarea>
    <div class="row" style="margin:0">
      <button class="go" id="b-go" style="flex:1">Разбить на шаги</button>
      <button class="small" id="b-mic">Голос</button>
    </div>
    <div class="lbox" id="lbox"></div>
  </section>

  <section id="s-run" class="col" hidden>
    <div id="bar"></div>
    <canvas id="cv"></canvas>
    <div class="card col" id="card">
      <div style="display:flex;justify-content:space-between">
        <span class="sub" id="cnt"></span>
        <span id="tm"></span>
      </div>
      <div id="title"></div>
      <div id="chk"></div>
      <div class="row" style="margin:0">
        <button class="go" id="b-ok" style="flex:2">Сделано</button>
        <button class="stuck" id="b-st" style="flex:1">Застрял</button>
      </div>
    </div>
  </section>

  <section id="s-done" class="card col" hidden>
    <h1>Готово</h1>
    <p class="sub" id="sum"></p>
    <button class="go" id="b-new">Новая цель</button>
  </section>

  <div class="row" style="margin:0">
    <button class="small" id="b-exp">Экспорт правил</button>
    <button class="small" id="b-clr">Сбросить правила</button>
  </div>
</main>
<div id="toast"></div>

<script>
const $=id=>document.getElementById(id)
const rd=(k,d)=>{try{return JSON.parse(localStorage.getItem(k))??d}catch{return d}}
const wr=(k,v)=>{try{localStorage.setItem(k,JSON.stringify(v))}catch{}}
const DEF={openai:'gpt-4o-mini',anthropic:'claude-haiku-5-5',openrouter:'openai/gpt-4o-mini'}
const cfg=rd('cfg',{p:'openai',m:'',snd:true,c3:false,anc:'off',url:''})
let st=rd('st',null), les=rd('les',[]), tick=null, t0=0, ac=null, th=null

function toast(m){
  const t=$('toast');t.textContent=m;t.classList.add('on')
  clearTimeout(toast.h);toast.h=setTimeout(()=>t.classList.remove('on'),3500)
}
function sv(){
  cfg.p=$('prov').value;cfg.m=$('model').value.trim();cfg.snd=$('snd').checked
  cfg.c3=$('c3').checked;cfg.anc=$('ancsel').value;wr('cfg',cfg)
}
const getKey=()=>{try{return localStorage.getItem('k')||sessionStorage.getItem('k')||''}catch{return ''}}
function setKey(v){
  try{
    localStorage.removeItem('k');sessionStorage.removeItem('k')
    ;($('rem').checked?localStorage:sessionStorage).setItem('k',v)
  }catch{}
}

// провайдеры различаются только форматом запроса и местом, где лежит текст ответа
async function ask(sys,usr){
  const p=$('prov').value, key=getKey(), model=$('model').value.trim()||DEF[p]
  if(!key)throw new Error('Нет ключа в настройках')
  const h={'Content-Type':'application/json'}
  let url,body
  if(p==='anthropic'){
    url='https://api.anthropic.com/v1/messages'
    h['x-api-key']=key;h['anthropic-version']='2023-06-01'
    h['anthropic-dangerous-direct-browser-access']='true'
    body={model,max_tokens:1024,system:sys,messages:[{role:'user',content:usr}]}
  }else{
    url=p==='openrouter'?'https://openrouter.ai/api/v1/chat/completions':'https://api.openai.com/v1/chat/completions'
    h.Authorization='Bearer '+key
    body={model,response_format:{type:'json_object'},messages:[{role:'system',content:sys},{role:'user',content:usr}]}
  }
  const r=await fetch(url,{method:'POST',headers:h,body:JSON.stringify(body)})
  const d=await r.json().catch(()=>({}))
  if(!r.ok)throw new Error((d.error&&d.error.message)||('HTTP '+r.status))
  const t=p==='anthropic'?(d.content&&d.content[0]&&d.content[0].text):(d.choices&&d.choices[0]&&d.choices[0].message.content)
  const m=String(t||'').match(/\{[\s\S]*\}/)
  if(!m)throw new Error('Модель вернула не JSON')
  return JSON.parse(m[0])
}

const tok=s=>new Set(String(s).toLowerCase().match(/[\p{L}\p{N}]{3,}/gu)||[])
function sim(a,b){
  const A=tok(a),B=tok(b);let n=0
  A.forEach(w=>{if(B.has(w))n++})
  return n/Math.max(1,Math.min(A.size,B.size))
}
function addLes(x){
  if(!x||!x.when||!x.do)return
  const l={when:String(x.when).slice(0,160),if:String(x.if||'').slice(0,160),do:String(x.do).slice(0,200),check:String(x.check||'').slice(0,160),n:1,t:Date.now()}
  const same=les.find(o=>sim(o.when+' '+o.do,l.when+' '+l.do)>0.6)
  if(same){same.n++;same.t=l.t}else les.push(l)
  if(les.length>60){const i=les.findIndex(o=>o.n<2);les.splice(i<0?0:i,1)}
  wr('les',les);showLes()
}
function pick(goal){
  const r=les.filter(l=>l.n>=2).map(l=>[sim(goal,l.when+' '+l.do),l]).sort((a,b)=>b[0]-a[0]||b[1].t-a[1].t)
  const hit=r.filter(x=>x[0]>0)
  return (hit.length?hit.slice(0,5):r.slice(0,2)).map(x=>x[1])
}
function showLes(){
  const el=$('lbox'), pr=les.filter(l=>l.n>=2)
  el.textContent=''
  const h=document.createElement('b')
  h.textContent='Правила: '+pr.length+', кандидаты: '+(les.length-pr.length)
  el.appendChild(h)
  pr.slice(-3).forEach(l=>{const d=document.createElement('div');d.textContent='Когда '+l.when+': '+l.do;el.appendChild(d)})
}

const RULES=`Rules for every step:
- One physical action, imperative verb first, at most 12 words, no preamble.
- Step 1 needs almost no effort: open something, touch something.
- Each step gets "secs": realistic seconds for this person, 15 to 180. No vague time.
- "verification" is a visible or audible sign that the step is done.
- Plain, matter-of-fact tone. No praise, no guilt, no filler.
- Write in the language of the goal.`
function dsys(goal){
  const p=pick(goal).map(l=>'- WHEN '+l.when+(l.if?' IF '+l.if:'')+' DO '+l.do+(l.check?' (check: '+l.check+')':'')).join('\n')
  return 'You split a goal into 3-6 micro-steps for a person with executive dysfunction.\n'+RULES+'\nLearned rules about this person, follow them:\n'+(p||'none yet')+'\nReturn only JSON: {"steps":[{"action":"","verification":"","secs":60}]}'
}
const SSYS='The person froze on a step. Split it into 2-3 smaller steps, each under 60 seconds, the first one nearly effortless.\n'+RULES+'\nAlso return one reusable lesson about what the planner must change next time for steps like this.\nReturn only JSON: {"steps":[{"action":"","verification":"","secs":30}],"lesson":{"when":"situation","if":"signal","do":"what to do","check":"how to tell it worked"}}'

const norm=x=>({a:String(x.action||x.a||'').slice(0,200),v:String(x.verification||x.v||'').slice(0,160),s:Math.min(180,Math.max(15,+x.secs||+x.s||60))})
const view=k=>['in','run','done'].forEach(n=>{$('s-'+n).hidden=n!==k})
async function busy(f,b){b.disabled=true;try{await f()}finally{b.disabled=false}}

async function go(){
  const goal=$('goal').value.trim()
  if(!goal)return toast('Напиши цель')
  try{
    const r=await ask(dsys(goal),goal)
    const steps=(r.steps||[]).map(norm).filter(s=>s.a)
    if(!steps.length)throw new Error('Пустой ответ модели')
    st={goal,steps,i:0,t0:Date.now()}
    wr('st',st);show()
  }catch(e){toast(e.message)}
}
function show(){
  if(!st||st.i>=st.steps.length)return fin()
  view('run')
  const s=st.steps[st.i]
  $('cnt').textContent=(st.i+1)+' из '+st.steps.length
  $('title').textContent=s.a
  $('chk').textContent=s.v?'Готово, когда: '+s.v:''
  const bar=$('bar');bar.textContent=''
  st.steps.forEach((_,i)=>{const e=document.createElement('i');e.className=i<st.i?'d':i===st.i?'c':'';bar.appendChild(e)})
  t0=Date.now();clearInterval(tick);tick=setInterval(clock,1000);clock()
  draw3()
}
function clock(){
  const s=st&&st.steps[st.i];if(!s)return
  const e=Math.floor((Date.now()-t0)/1000)
  const f=x=>Math.floor(x/60)+':'+String(x%60).padStart(2,'0')
  $('tm').textContent=f(e)+' / '+f(s.s)
  $('tm').classList.toggle('over',e>s.s)
}
function ok(){
  beep()
  const c=$('card');c.classList.remove('flash');void c.offsetWidth;c.classList.add('flash')
  st.i++;wr('st',st);show()
}
async function stuck(){
  const s=st.steps[st.i]
  let subs=null
  try{
    const r=await ask(SSYS,JSON.stringify({goal:st.goal,step:s.a}))
    subs=(r.steps||[]).map(norm).filter(x=>x.a).slice(0,3)
    addLes(r.lesson)
  }catch(e){toast(e.message)}
  // без связи человек всё равно получает что-то сделать, а не пустой экран
  if(!subs||!subs.length)subs=[{a:'Открой нужный файл или окно и больше ничего не делай',v:'окно открыто',s:30}]
  st.steps.splice(st.i,1,...subs)
  wr('st',st);show()
}
function fin(){
  clearInterval(tick)
  const m=Math.max(1,Math.round((Date.now()-(st?st.t0:Date.now()))/60000))
  $('sum').textContent='Шагов: '+(st?st.steps.length:0)+', примерно '+m+' мин.'
  try{localStorage.removeItem('st')}catch{}
  st=null;view('done')
}

function beep(){
  if(!$('snd').checked)return
  const C=window.AudioContext||window.webkitAudioContext;if(!C)return
  ac=ac||new C()
  const o=ac.createOscillator(),g=ac.createGain()
  o.frequency.value=660;g.gain.value=0.04
  o.connect(g);g.connect(ac.destination);o.start();o.stop(ac.currentTime+0.09)
}
function startNoise(){
  const C=window.AudioContext||window.webkitAudioContext;if(!C)return
  ac=ac||new C();ac.resume()
  const n=ac.sampleRate*2,b=ac.createBuffer(1,n,ac.sampleRate),d=b.getChannelData(0)
  let l=0
  for(let i=0;i<n;i++){l=(l+0.02*(Math.random()*2-1))/1.02;d[i]=l*3.5}
  const s=ac.createBufferSource(),g=ac.createGain()
  s.buffer=b;s.loop=true;g.gain.value=0.15
  s.connect(g);g.connect(ac.destination);s.start()
  startNoise.s=s
}
function stopNoise(){try{startNoise.s&&startNoise.s.stop()}catch{};startNoise.s=null}
function anchor(){
  const v=$('ancsel').value,box=$('anc')
  box.textContent='';stopNoise()
  if(v==='noise')startNoise()
  if(v==='video'){
    const i=document.createElement('input')
    i.type='text';i.placeholder='Ссылка на YouTube';i.value=cfg.url||'';i.style.width='100%';i.style.marginTop='10px'
    i.onchange=()=>{cfg.url=i.value;wr('cfg',cfg);anchor()}
    box.appendChild(i)
    const m=(cfg.url||'').match(/(?:v=|youtu\.be\/|embed\/)([\w-]{11})/)
    if(m){
      const f=document.createElement('iframe')
      f.allow='autoplay'
      f.src='https://www.youtube-nocookie.com/embed/'+m[1]+'?autoplay=1&mute=1&loop=1&controls=0&playlist='+m[1]
      box.appendChild(f)
    }
  }
}

// Three.js грузится только когда граф включён, и размер берётся после показа канваса
async function draw3(){
  const cv=$('cv')
  if(!$('c3').checked||!st){cv.style.display='none';return}
  cv.style.display='block'
  if(!window.THREE){
    await new Promise((y,n)=>{
      const s=document.createElement('script')
      s.src='https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js'
      s.onload=y;s.onerror=n;document.head.appendChild(s)
    }).catch(()=>{})
    if(!window.THREE){$('c3').checked=false;sv();cv.style.display='none';return toast('Three.js не загрузился')}
  }
  if(!th){
    const T=THREE,r=new T.WebGLRenderer({canvas:cv,antialias:true,alpha:true})
    const sc=new T.Scene(),cam=new T.PerspectiveCamera(45,1,.1,100),g=new T.Group()
    cam.position.z=6;sc.add(g)
    th={T,r,sc,cam,g}
    const spin=!matchMedia('(prefers-reduced-motion: reduce)').matches
    const loop=()=>{
      requestAnimationFrame(loop)
      if(!$('c3').checked||document.hidden||!st)return
      if(spin)g.rotation.y+=.008
      r.render(sc,cam)
    }
    loop()
  }
  const w=cv.clientWidth,h=cv.clientHeight
  th.r.setSize(w,h,false);th.cam.aspect=w/h;th.cam.updateProjectionMatrix()
  const {T,g}=th,n=st.steps.length,gap=Math.min(1.2,5/n),x0=-(n-1)*gap/2
  while(g.children.length){
    const o=g.children[0]
    o.geometry&&o.geometry.dispose();o.material&&o.material.dispose();g.remove(o)
  }
  st.steps.forEach((_,i)=>{
    const cur=i===st.i,col=i<st.i?0x22c55e:cur?0xffffff:0x2e3440
    const m=new T.Mesh(new T.IcosahedronGeometry(cur?.35:.22,1),new T.MeshBasicMaterial({color:col,wireframe:true}))
    m.position.x=x0+i*gap;g.add(m)
  })
}

function mic(){
  const R=window.SpeechRecognition||window.webkitSpeechRecognition
  if(!R)return toast('Диктовка здесь не поддерживается')
  const r=new R();r.lang=navigator.language||'ru-RU'
  r.onresult=e=>{const g=$('goal');g.value+=(g.value?' ':'')+e.results[0][0].transcript}
  r.onerror=()=>toast('Не расслышал, попробуй ещё раз')
  r.start()
}
function exp(){
  const a=document.createElement('a')
  a.href=URL.createObjectURL(new Blob([JSON.stringify(les,null,1)],{type:'application/json'}))
  a.download='rules.json';a.click()
}

$('prov').value=cfg.p;$('model').value=cfg.m||DEF[cfg.p]
$('snd').checked=cfg.snd;$('c3').checked=cfg.c3;$('ancsel').value=cfg.anc
$('key').value=getKey()
try{$('rem').checked=!!localStorage.getItem('k')}catch{}
$('set').open=!getKey()
$('prov').onchange=()=>{$('model').value=DEF[$('prov').value];sv()}
$('model').onchange=sv;$('snd').onchange=sv
$('ancsel').onchange=()=>{sv();anchor()}
$('c3').onchange=()=>{sv();draw3()}
$('key').onchange=$('rem').onchange=()=>setKey($('key').value.trim())
$('b-go').onclick=()=>busy(go,$('b-go'))
$('b-ok').onclick=ok
$('b-st').onclick=()=>busy(stuck,$('b-st'))
$('b-new').onclick=()=>{$('goal').value='';view('in')}
$('b-mic').onclick=mic
$('b-exp').onclick=exp
$('b-clr').onclick=()=>{if(confirm('Удалить все правила?')){les=[];wr('les',les);showLes()}}
document.addEventListener('click',()=>{if($('ancsel').value==='noise'&&!startNoise.s)startNoise()},{once:true})
showLes();view('in')
if(st&&st.steps&&st.i<st.steps.length)show();else st=null
if($('ancsel').value==='video')anchor()
</script>
</body>
</html>
```

---

## 7. Что изменено относительно первой версии

Баги:

- 3D-канвас теперь измеряется после показа, раньше он создавался внутри скрытого блока с нулевой шириной и оставался пустым.
- Ответы API проверяются: неверный ключ, лимиты, не-JSON выдают понятное сообщение в тихом тосте, а не `undefined` в alert.
- Всё, что приходит от модели, выводится через `textContent`. Раньше правила шли в `innerHTML`, а это уязвимость.
- Прогресс сессии хранится в localStorage и переживает перезагрузку.
- Нет alert() в момент срыва. Остался один confirm() на удаление правил, он вызывается только осознанным кликом.
- Плейлисты YouTube убраны: ID в первой версии выглядели выдуманными. Теперь человек сам вставляет ссылку.
- Схема правила в коде теперь совпадает со схемой в спеке: when, if, do, check.

Недостатки в самой идее:

- Кнопка "Застрял" раньше подставляла один и тот же текст. Теперь модель режет конкретный шаг на два-три подшага.
- Один срыв больше не создаёт правило: нужен повтор (раздел 4).
- В промпт попадают до пяти подходящих правил, а не все подряд.
- Добавлены таймер шага, награда за каждый шаг, диктовка, экспорт правил.
- Сенсорный фон и 3D-граф стали опциями и по умолчанию выключены.
- Провайдеров три, а не один.
- Явная пометка, что это не медицинский инструмент, и честная заметка о хранении ключа.

Что не исправлено намеренно: ключ по-прежнему хранится открытым текстом. Шифровать его в браузере без пароля пользователя бессмысленно, любой скрипт на странице прочитает и ключ, и расшифровку. По умолчанию ключ лежит в sessionStorage и исчезает при закрытии вкладки, в localStorage он попадает только если поставить галочку.

---

## 8. План и как проверять, что это работает

**Фаза 0, неделя на себе.** Пользоваться ежедневно и смотреть: сколько раз застрял, какие правила родились, не раздражают ли подсказки. Если за неделю ни одно правило не дошло до n = 2, механика повышения слишком строга или срывы слишком разнообразны.

**Фаза 1, метрики локально.** Время до первого шага, доля завершённых целей, число срывов на сессию. Считать в localStorage и никуда не отправлять. Нужен офлайн-каркас (PWA с service worker), чтобы страница открывалась без сети.

**Фаза 2, несколько живых людей.** Пять-десять человек с СДВГ, которые согласны попробовать. Смотреть не на отзывы, а на то, вернулись ли они на третий день.

**Фаза 3, если фазы 0-2 дали сигнал.**
- Эмбеддинги вместо пересечения слов для отбора и слияния правил (пакет проверить, см. раздел 2).
- Режим обучения по мотивам learnharness: измерить, что человек уже знает, и учить одним маленьким шагом.
- Мост к локальной системе (MCP) из первой версии стоит считать отдельным проектом. Страница в браузере не может сама проверять терминал и открытые приложения, нужен локальный демон, а это другая модель безопасности. В MVP не входит.

---

## 9. Ограничения и риски

- Модель может выдать шаг, который не подходит или звучит глупо. Поэтому всегда есть "Застрял" и шаги короткие.
- Цели уходят выбранному провайдеру. Человеку с чувствительными задачами это надо сказать прямо, до первого запуска.
- Видео-фон грузится со стороннего сервиса и может отвлекать. Данных, что он помогает, у меня нет.
- Приложение не заменяет врача, терапию или коучинг. Оно уменьшает порог входа в конкретную задачу, не больше.
- Оценки конкурентов и утверждения о существующих проектах в разделах 1 и 2 основаны на поиске в один день и на моей памяти. Перед публичным питчем их надо перепроверить.
