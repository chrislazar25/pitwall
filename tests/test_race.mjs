import assert from "node:assert/strict";
import { test } from "node:test";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import { race, askMatchesLap, linkAgent, TYRE_COLORS, RATING_COLORS } from "../mods/racetrack/model.js";

const now = Date.parse("2026-11-16T20:00:00Z");
const at = (hours) => new Date(now - hours * 3600000).toISOString();
const agents = [
  { key: "other", programKey: "codex", programName: "Codex", spaceName: "docs", status: "blocked" },
  { key: "project", programKey: "codex", programName: "Codex", spaceName: "pitwall", status: "working" },
  { key: "second", programKey: "codex", spaceName: "pitwall", status: "idle" },
  { key: "claude", programKey: "claude-code", spaceName: "pitwall", status: "working" },
];
const drivers = {
  codex: { program: "codex", color: "#3b82f6", tyre: "medium" },
  claude: { program: "claude-code", color: "#e8743b", tyre: "soft" },
  "glm-flash": { program: null, color: "#22c55e", tyre: "hard" },
};
const lap = (key = "l1", agent = "codex", hours = 1) => ({ lap: key, title: `Build ${key}`,
  project: "pitwall", agent, started_at: at(hours) });
const ask = (id = "a1", overrides = {}) => ({ id, type: "taste", headline: "Choose", agent: "codex",
  project: "pitwall", asked_at: at(0.25), lap: null, ...overrides });
const result = (key = "done", ageMs = 0) => ({ lap: key, title: `Shipped ${key}`, project: "pitwall",
  agent: "claude", hours: 0.5, shipped_at: new Date(now - ageMs).toISOString(), rating: "best" });
const state = (running = [lap()]) => ({ drivers, event_count: 1, open_asks: [],
  laps: { running, pace_hours: 4, last: null, last_hours: null, best_hours: null } });
const view = (snapshot, ordered = agents, clock = now) => race(JSON.stringify(snapshot), ordered, clock);

test("clock wraps precisely, counts repeated clock laps, and clamps future starts", () => {
  const model = view(state([lap("one", "codex", 4), lap("two", "codex", 9), lap("future", "codex", -1)]));
  assert.deepEqual(model.cars.map(({ fraction, completedLaps, elapsedHours }) =>
    [fraction, completedLaps, elapsedHours]), [[0, 1, 4], [0.25, 2, 9], [0, 0, 0]]);
  const zero = state();
  zero.laps.pace_hours = 0;
  assert.equal(view(zero).cars[0].fraction, 0);
  assert.equal(view(zero).cars[0].completedLaps, 0);
  for (const pace of [-1, null, "4"]) {
    zero.laps.pace_hours = pace;
    assert.equal(view(zero).cars[0].fraction, 0.25);
  }
});

test("pit association is literal lap OR nonnull matching agent and project", () => {
  assert.ok(askMatchesLap(ask("explicit", { lap: "legacy", agent: "other" }), lap("legacy", null)));
  assert.ok(askMatchesLap(ask("different", { lap: "other-lap" }), lap()));
  assert.ok(!askMatchesLap(ask("none", { agent: null }), lap("legacy", null)));
  assert.ok(!askMatchesLap(ask("wrong-project", { project: "elsewhere" }), lap()));
  const snapshot = state();
  snapshot.open_asks = [ask("young"), ask("old", { asked_at: at(1.75) })];
  const inPit = view(snapshot).cars[0];
  assert.equal(inPit.mode, "pit");
  assert.equal(inPit.waitingMinutes, 105);
  snapshot.open_asks = [];
  const onTrack = view(snapshot).cars[0];
  assert.equal(onTrack.mode, "track");
  assert.equal(onTrack.fraction, inPit.fraction);
});

test("every waiting lap gets a physical bay and overflow stack", () => {
  const snapshot = state(Array.from({ length: 14 }, (_, i) => lap(`l${i}`)));
  snapshot.open_asks = [ask()];
  const cars = view(snapshot).cars;
  assert.equal(cars.length, 14);
  assert.ok(cars.every((car) => car.mode === "pit" && car.bay >= 0 && car.bay < 6));
  assert.equal(new Set(cars.map((car) => `${car.bay}:${car.stack}`)).size, 14);
  assert.deepEqual(cars.map((car) => [car.bay, car.stack]),
    cars.map((_, i) => [i % 6, Math.floor(i / 6)]));
});

test("terminal mapping prefers the first project match then the first program match", () => {
  assert.equal(linkAgent(lap(), drivers, agents).key, "project");
  assert.equal(linkAgent({ ...lap(), project: "missing" }, drivers, agents).key, "other");
  for (const name of [null, "unknown", "glm-flash"]) assert.equal(linkAgent(lap("l", name), drivers, agents), null);
  assert.equal(linkAgent(lap(), drivers, []), null);
  const model = view(state([lap(), lap("l2")]));
  assert.equal(model.cars[0].terminal, "project");
  assert.deepEqual(model.garage.map((a) => a.key), ["other", "second", "claude"]);
});

test("configured colors and prescribed tyres survive without guessing legacy drivers", () => {
  const model = view(state([lap("c", "claude"), lap("x"), lap("g", "glm-flash"), lap("old", null)]));
  assert.deepEqual(model.cars.map((car) => [car.livery, car.tyreColor]), [
    ["#e8743b", "#ef4444"], ["#3b82f6", "#eab308"], ["#22c55e", "#f5f5f5"], [null, null],
  ]);
  assert.equal(model.cars[3].terminal, null);
  assert.equal(model.cars[3].title, "Build old");
  const custom = state();
  custom.drivers = { codex: { program: null, color: "#123456", tyre: "hard" } };
  assert.equal(view(custom).cars[0].livery, "#123456");
  assert.equal(view(custom).cars[0].terminal, null);
  assert.deepEqual(TYRE_COLORS, { soft: "#ef4444", medium: "#eab308", hard: "#f5f5f5" });
  assert.deepEqual(RATING_COLORS, { best: "#a855f7", good: "#22c55e", slow: "#eab308" });
});

test("all nonfuture finishes expire on the live ten minute boundary", () => {
  const snapshot = state([]);
  snapshot.laps.finished = [result("new"), result("boundary", 600000), result("expired", 600001), result("future", -1)];
  snapshot.laps.last = snapshot.laps.finished[0];
  const model = view(snapshot);
  assert.deepEqual(model.cars.map((car) => car.key), ["new", "boundary"]);
  assert.ok(model.cars.every((car) => car.mode === "finished" && car.rating === "best" && car.hours === 0.5));
  assert.equal(model.garage.length, agents.length);
  assert.equal(view(snapshot, agents, now + 600001).cars.length, 1);
  delete snapshot.laps.finished;
  assert.equal(view(snapshot).cars[0].key, "new");
});

test("flags apply exact overdue, no working agent, recent finish, green precedence", () => {
  const snapshot = state([]);
  snapshot.laps.finished = [result()];
  snapshot.open_asks = [ask("boundary", { asked_at: at(0.5) })];
  assert.equal(view(snapshot).flag, "chequered");
  assert.equal(view(snapshot, []).flag, "red");
  snapshot.open_asks[0].asked_at = new Date(now - 1800001).toISOString();
  assert.equal(view(snapshot, []).flag, "yellow");
  snapshot.open_asks = [];
  snapshot.laps.finished = [];
  assert.equal(view(snapshot).flag, "green");
  assert.equal(view(snapshot, agents.map((agent) => ({ ...agent, status: "idle" }))).flag, "red");
  snapshot.pit_stops = { fastest_today_minutes: 0 };
  assert.equal(view(snapshot).fastestPitMinutes, 0);
});

test("legacy optional fields remain usable and malformed core never invents an empty race", () => {
  const legacy = { open_asks: [], laps: { running: [{ lap: "old", title: "Legacy", started_at: at(1) }] } };
  const model = view(legacy);
  assert.equal(model.data, "ready");
  assert.equal(model.cars[0].fraction, 0.25);
  assert.equal(model.cars[0].livery, null);
  assert.deepEqual(model.garage, agents);
  for (const bad of [null, "", "{", "[]", "{}", "null", JSON.stringify({ ...state(), open_asks: [null] }),
    JSON.stringify(state([{ ...lap(), started_at: "broken" }])), JSON.stringify(state([{ ...lap(), agent: 1 }]))]) {
    const unavailable = race(bad, agents, now);
    assert.equal(unavailable.data, "no-data");
    assert.equal(unavailable.flag, null);
    assert.deepEqual(unavailable.cars, []);
    assert.deepEqual(unavailable.garage, agents);
  }
});

test("accepted centerline remains closed, measured by length, and fitted inside the block", () => {
  const source = readFileSync(new URL("../mods/racetrack/main.js", import.meta.url), "utf8");
  const geometry = source.slice(source.indexOf("export const VIEWBOX"), source.indexOf("export default class"))
    .replaceAll("export ", "");
  const { CENTERLINE, TRACK_LENGTH, pointAtFraction, fitCircuit } = vm.runInNewContext(
    geometry + "; ({CENTERLINE,TRACK_LENGTH,pointAtFraction,fitCircuit})");
  assert.ok(CENTERLINE.length >= 24);
  assert.ok(TRACK_LENGTH > 1500);
  assert.deepEqual(pointAtFraction(0), pointAtFraction(1));
  assert.deepEqual(pointAtFraction(0.25), pointAtFraction(2.25));
  assert.ok(Math.abs(pointAtFraction(0).x - 510) < 1e-8);
  for (const [width, height] of [[1000, 500], [500, 300], [0, 0]]) {
    const fit = fitCircuit(width, height);
    assert.ok(fit.width <= width && fit.height <= height);
    assert.ok(fit.scale >= 0);
  }
});
