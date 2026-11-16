import assert from "node:assert/strict";
import { test } from "node:test";
import { tower } from "../mods/pitwall/model.js";

const now = Date.parse("2026-11-16T20:00:00Z");
const grid = [
  { key: "t2", programName: "Codex", spaceName: "pitwall", status: "working" },
  { key: "t1", programName: "Claude", spaceName: "docs", status: "blocked" },
];
const empty = () => ({
  open_asks: [],
  laps: { running: [], last_hours: null, best_hours: null },
  scores: { speed: null, ask_quality: null, shipping: null, ownership: null },
});
const ask = (id, asked_at) => ({
  id, type: "taste", headline: "Dock the timing tower", project: "pitwall", agent: "codex", asked_at,
});
const view = (state) => tower(JSON.stringify(state), grid, now);
const fuel = () => ({
  tokens_today: 35639818,
  tokens_7d: 149876543,
  by_tool_7d: [{ tool: "claude", tokens: 74876543 }, { tool: "codex", tokens: 75000000 }],
  api_value_30d_usd: 847.25,
  out_of_pocket_month_usd: 200,
  value_ratio: 4.23625,
});

test("missing and malformed snapshots retain the grid without claiming an empty queue", () => {
  for (const text of [null, "", "{", "null", "[]", "{}", "42"]) {
    const result = tower(text, grid, now);
    assert.equal(result.data, "no-data");
    assert.equal(result.openCount, null);
    assert.deepEqual(result.grid, grid.map((agent, index) => ({ ...agent, position: index + 1 })));
    assert.deepEqual(result.asks, []);
    assert.deepEqual(result.laps, []);
    assert.equal(result.fuel, null);
    assert.ok(result.sectors.every((sector) => sector.value === null));
  }
});

test("valid empty data displays zero asks and legitimate null scores and lap summaries", () => {
  const result = view(empty());
  assert.equal(result.data, "ready");
  assert.equal(result.openCount, 0);
  assert.deepEqual(result.asks, []);
  assert.deepEqual(result.laps, []);
  assert.equal(result.lastHours, null);
  assert.equal(result.bestHours, null);
  assert.equal(result.fuel, null);
  assert.deepEqual(result.sectors, ["SPEED", "ASKS", "SHIP", "OWN"].map((label) => ({ label, value: null })));
});

test("malformed queue, lap or sector fields make the snapshot unavailable", () => {
  const changes = [
    (s) => { delete s.open_asks; },
    (s) => { s.open_asks = {}; },
    (s) => { s.open_asks = [null]; },
    (s) => { s.open_asks = [ask("a1", "not a date")]; },
    (s) => { s.open_asks = [{ ...ask("a1", "2026-11-16T19:00:00Z"), project: null }]; },
    (s) => { s.open_asks = [ask("a1", 1794855600000)]; },
    (s) => { s.laps = null; },
    (s) => { s.laps.running = {}; },
    (s) => { s.laps.running = [{ lap: "l1", title: "Build", started_at: "no" }]; },
    (s) => { s.laps.running = [{ title: "Build", started_at: "2026-11-16T19:00:00Z" }]; },
    (s) => { s.laps.last_hours = -1; },
    (s) => { s.laps.best_hours = "1"; },
    (s) => { delete s.laps.best_hours; },
    (s) => { s.scores = []; },
    (s) => { delete s.scores.ownership; },
    (s) => { s.scores.speed = -1; },
    (s) => { s.scores.ask_quality = 101; },
    (s) => { s.scores.shipping = "10"; },
  ];
  for (const change of changes) {
    const state = empty();
    change(state);
    const result = view(state);
    assert.equal(result.data, "no-data", change.toString());
    assert.equal(result.openCount, null);
  }
});

test("asks preserve source order and use exact elapsed time for the overdue boundary", () => {
  const state = empty();
  state.open_asks = [
    ask("exact", "2026-11-16T19:30:00Z"),
    ask("over", "2026-11-16T19:29:59Z"),
    ask("older", "2026-11-16T19:29:00Z"),
    ask("future", "2026-11-16T20:05:00Z"),
  ];
  const result = view(state);
  assert.equal(result.openCount, 4);
  assert.deepEqual(result.asks.map((a) => [a.key, a.waitingMinutes, a.overdue]), [
    ["exact", 30, false], ["over", 30, true], ["older", 31, true], ["future", 0, false],
  ]);
  assert.deepEqual(result.asks[0], {
    key: "exact", type: "taste", headline: "Dock the timing tower", project: "pitwall",
    agent: "codex", waitingMinutes: 30, overdue: false,
  });
});

test("laps use the producer's lap field, preserve order, and clamp future starts", () => {
  const state = empty();
  state.laps = {
    running: [
      { lap: "l-build", title: "Build the tower", started_at: "2026-11-16T18:30:00Z" },
      { lap: "l-next", title: "Next lap", started_at: "2026-11-16T21:00:00Z" },
    ],
    last_hours: 2.25,
    best_hours: 0,
  };
  const result = view(state);
  assert.deepEqual(result.laps, [
    { key: "l-build", title: "Build the tower", elapsedHours: 1.5 },
    { key: "l-next", title: "Next lap", elapsedHours: 0 },
  ]);
  assert.equal(result.lastHours, 2.25);
  assert.equal(result.bestHours, 0);
});

test("sectors read the actual projection field names and accept the legacy fuel placeholder", () => {
  const state = empty();
  state.scores = { speed: 0, ask_quality: 25, shipping: 62.5, ownership: 100 };
  Object.assign(state, { generated_at: "ignored", fuel: {}, garage: 5, radio: false });
  const result = view(state);
  assert.equal(result.data, "ready");
  assert.equal(result.fuel, null);
  assert.deepEqual(result.sectors, [
    { label: "SPEED", value: 0 }, { label: "ASKS", value: 25 },
    { label: "SHIP", value: 62.5 }, { label: "OWN", value: 100 },
  ]);
});

test("fuel exposes exact usage counts and spend without adding cached input again", () => {
  const state = { ...empty(), fuel: fuel() };
  const result = view(state);
  assert.equal(result.data, "ready");
  assert.deepEqual(result.fuel, fuel());
});

test("zero fuel and a null value ratio remain valid data", () => {
  const zero = {
    tokens_today: 0, tokens_7d: 0, by_tool_7d: [{ tool: "codex", tokens: 0 }],
    api_value_30d_usd: 0, out_of_pocket_month_usd: 0, value_ratio: null,
  };
  assert.deepEqual(view({ ...empty(), fuel: zero }).fuel, zero);
  assert.equal(view({ ...empty(), fuel: { ...zero, out_of_pocket_month_usd: 200, value_ratio: 0 } }).fuel.value_ratio, 0);
});

test("invalid or missing fuel degrades only fuel while preserving asks and laps", () => {
  const state = empty();
  state.open_asks = [ask("a1", "2026-11-16T19:00:00Z")];
  state.laps = {
    running: [{ lap: "l1", title: "Build", started_at: "2026-11-16T18:30:00Z" }],
    last_hours: 1, best_hours: 0,
  };
  const baseline = view(state);
  const invalid = [undefined, null, {}, [], "fuel", 0,
    ...["tokens_today", "tokens_7d", "by_tool_7d", "api_value_30d_usd",
      "out_of_pocket_month_usd", "value_ratio"].map((key) => {
      const incomplete = fuel();
      delete incomplete[key];
      return incomplete;
    }),
    { ...fuel(), extra: true },
    { ...fuel(), tokens_today: -1 },
    { ...fuel(), tokens_7d: 1.5 },
    { ...fuel(), tokens_today: "1" },
    { ...fuel(), by_tool_7d: {} },
    { ...fuel(), by_tool_7d: [null] },
    { ...fuel(), by_tool_7d: [{ tool: 1, tokens: 3 }] },
    { ...fuel(), by_tool_7d: [{ tool: "codex", tokens: -1 }] },
    { ...fuel(), by_tool_7d: [{ tool: "codex", tokens: 0.5 }] },
    { ...fuel(), api_value_30d_usd: -1 },
    { ...fuel(), out_of_pocket_month_usd: "200" },
    { ...fuel(), value_ratio: -1 },
    { ...fuel(), value_ratio: "4x" },
  ];
  for (const summary of invalid) {
    const result = view({ ...state, fuel: summary });
    assert.deepEqual(result, baseline, JSON.stringify(summary));
  }
  const infinite = JSON.stringify({ ...state, fuel: fuel() }).replace('"api_value_30d_usd":847.25', '"api_value_30d_usd":1e999');
  assert.deepEqual(tower(infinite, grid, now), baseline);
});

test("elapsed text advances when the caller supplies a later clock", () => {
  const state = empty();
  state.open_asks = [ask("a1", "2026-11-16T19:59:30Z")];
  const text = JSON.stringify(state);
  assert.equal(tower(text, [], now).asks[0].waitingMinutes, 0);
  assert.equal(tower(text, [], now + 30000).asks[0].waitingMinutes, 1);
});
