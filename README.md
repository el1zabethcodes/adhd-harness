# Step Harness

A single-file app for people who freeze in front of a big, blurry task. It splits a goal into steps of one to three minutes, shows exactly one step at a time next to a step timer, and learns personal rules from the points where you get stuck. Press "Застрял" (stuck) and the current step is cut into smaller substeps; if a similar lapse happens twice, it becomes a working rule that shapes future splits.

This is not a medical device, not therapy, and not a replacement for a specialist. It lowers the entry barrier into one concrete task, nothing more.

The interface is in Russian. The full specification lives in [docs/spec.md](docs/spec.md).

## How to run

No build, no backend, no install. Save `index.html` and double-click it — it opens in the browser. Everything runs locally in that one page.

## API key

The app does not ship a key; you bring your own. Open **Настройки**, pick a provider (OpenAI, Anthropic or OpenRouter), paste your API key, and optionally change the model name.

The key is stored in the browser in plain text: in `sessionStorage` by default, which disappears when the tab closes, or in `localStorage` if you tick "помнить ключ". Any script running on the page could read it — that is the trade-off of a key in a browser page, and the spec keeps it knowingly.

## Where the data goes

The goal text and the current step are sent to the API of the provider you picked. Learned rules, session progress and settings stay in the browser's `localStorage`. Nothing is sent anywhere else. If a task is sensitive, know this before the first run.

## Attribution

The rules used in the prompts are based on the ten rules of the [ayghri/i-have-adhd](https://github.com/ayghri/i-have-adhd) project (MIT license).

## Tests

```
npm install
npm test
```

The only dependency is jsdom; the tests stub `fetch` and touch no network.

## License

AGPL-3.0, see [LICENSE](LICENSE).
