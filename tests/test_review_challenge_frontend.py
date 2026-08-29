import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_JS = ROOT / "french_learning" / "static" / "app.js"


class ReviewChallengeFrontendTest(unittest.TestCase):
    def run_javascript(self, scenario):
        harness = f"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const storage = new Map();
const inertElement = {{
  textContent: '', className: '', innerHTML: '', disabled: false,
  querySelectorAll: () => [], querySelector: () => null,
  addEventListener: () => {{}}, classList: {{toggle: () => {{}}}}
}};
const context = {{
  console, assert, Intl, Date, Promise, URL, Math,
  fetch: () => new Promise(() => {{}}),
  localStorage: {{
    getItem: key => storage.has(key) ? storage.get(key) : null,
    setItem: (key, value) => storage.set(key, String(value)),
    removeItem: key => storage.delete(key)
  }},
  document: {{
    querySelector: selector => selector === '#view' || selector === '#status' ? inertElement : null,
    querySelectorAll: () => []
  }},
  window: {{innerWidth: 1200, scrollTo: () => {{}}}},
  Audio: function () {{}},
  setInterval, clearInterval, setTimeout,
  confirm: () => true
}};
vm.createContext(context);
vm.runInContext(fs.readFileSync({json.dumps(str(APP_JS))}, 'utf8'), context);
vm.runInContext({json.dumps(scenario)}, context);
"""
        return subprocess.run(
            ["node", "-e", harness],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_question_is_shown_at_most_twice_per_day(self):
        result = self.run_javascript("""
state.reviewMistakes = Array.from({length: 7}, (_, index) => ({id: index + 1}));
const appearances = {};
for (let run = 0; run < 10; run += 1) {
  if (!reviewChallengeCandidates().length) break;
  startReviewChallenge();
  for (const item of state.reviewChallenge.items) {
    appearances[item.id] = (appearances[item.id] || 0) + 1;
  }
  reviewChallengeUsageCache = null;
}
assert.ok(Object.values(appearances).length > 0);
assert.ok(Object.values(appearances).every(count => count <= 2), JSON.stringify(appearances));
""")
        self.assertEqual(0, result.returncode, result.stderr)

    def test_correct_question_can_be_removed_from_future_challenges(self):
        result = self.run_javascript("""
state.reviewMistakes = [{id: 41}, {id: 42}];
state.reviewChallenge = {
  items: [state.reviewMistakes[0]], index: 0, score: 1,
  answered: true, selected: 'juste', correct: true, finished: false
};
dismissReviewChallengeItem();
reviewChallengeDismissedCache = null;
assert.ok(reviewChallengeDismissedIds().has('41'));
assert.ok(!reviewChallengeCandidates().some(item => item.id === 41));
assert.ok(reviewChallengeCandidates().some(item => item.id === 42));
""")
        self.assertEqual(0, result.returncode, result.stderr)


if __name__ == "__main__":
    unittest.main()
