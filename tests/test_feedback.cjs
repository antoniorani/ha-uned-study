"use strict";

const assert = require("node:assert/strict");
const {readFileSync} = require("node:fs");
const {join} = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const appSource = readFileSync(
  join(__dirname, "../uned-study/app/uned_study/static/app.js"),
  "utf8"
);

function launchStudy(explanation = "") {
  const answerA = {dataset: {answer: "a"}};
  const answerB = {dataset: {answer: "b"}};
  const start = {dataset: {continue: "demo"}};
  const root = {
    innerHTML: "",
    querySelectorAll(selector) {
      if (selector === "[data-continue]" && this.innerHTML.includes('data-continue="demo"')) {
        return [start];
      }
      if (selector === "[data-answer]" && this.innerHTML.includes('data-answer="a"')) {
        return [answerA, answerB];
      }
      return [];
    },
  };
  const controls = new Map();
  const document = {
    baseURI: "http://localhost/",
    documentElement: {
      dataset: {},
      style: {setProperty() {}, removeProperty() {}},
    },
    getElementById(id) {
      if (id === "app") return root;
      if (!controls.has(id)) controls.set(id, {});
      return controls.get(id);
    },
  };
  const item = {
    id: "q1",
    type: "test",
    question_md: "¿Qué opción es correcta?",
    answers: [
      {id: "a", text_md: "**Opción válida**"},
      {id: "b", text_md: "Opción incorrecta"},
    ],
  };
  const response = (value) => ({ok: true, json: async () => value});
  const fetch = async (url, options = {}) => {
    if (url.endsWith("/api/dashboard")) {
      return response({
        subjects: [{id: "demo", title: "Demo", type: "test"}],
        content: {last_sync: "ok"},
      });
    }
    if (url.endsWith("/api/subjects/demo/continue")) {
      return response({session_id: "s1", kind: "study"});
    }
    if (url.endsWith("/api/sessions/s1/next")) {
      return response({item});
    }
    if (url.endsWith("/api/sessions/s1/answer")) {
      const {answer_id} = JSON.parse(options.body);
      return response({
        correct: answer_id === "a",
        item: {...item, correct_answer: "a", explanation_md: explanation},
      });
    }
    throw new Error("Unexpected API call: " + url);
  };
  const window = {
    frameElement: null,
    matchMedia: () => ({matches: false, addEventListener() {}}),
    addEventListener() {},
    setInterval() {},
  };
  vm.runInNewContext(appSource, {
    document, window, URL, fetch,
    performance: {now: () => 1000},
    crypto: {randomUUID: () => "request-id"},
  }, {filename: "app.js"});

  return {root, start, answerA, answerB};
}

async function answerQuestion(choice, explanation = "") {
  const app = launchStudy(explanation);
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(typeof app.start.onclick, "function");
  await app.start.onclick();
  assert.match(app.root.innerHTML, /¿Qué opción es correcta\?/);
  assert.doesNotMatch(app.root.innerHTML, /Respuesta correcta:/);
  await app[choice].onclick();
  return app.root.innerHTML;
}

test("incorrect test answer reveals the correct option without an explanation", async () => {
  const html = await answerQuestion("answerB");
  assert.match(html, /<h2>Incorrecta<\/h2>/);
  assert.match(html, /Respuesta correcta:/);
  assert.match(html, /<strong>Opción válida<\/strong>/);
});

test("incorrect test answer also retains the explanation", async () => {
  const html = await answerQuestion("answerB", "Por **este motivo**.");
  assert.match(html, /Respuesta correcta:/);
  assert.match(html, /Por <strong>este motivo<\/strong>\./);
});

test("correct test answer keeps its existing feedback", async () => {
  const html = await answerQuestion("answerA", "Bien **hecho**.");
  assert.match(html, /<h2>Correcta<\/h2>/);
  assert.doesNotMatch(html, /Respuesta correcta:/);
  assert.match(html, /Bien <strong>hecho<\/strong>\./);
});
