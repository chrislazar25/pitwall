import { View, div, image, svg } from "gpui-kit";
import { h_flex, v_flex } from "gpui-base";
import { agents, theme, props, home, readTextFile, watchFolder, run } from "herdr";

import { race, RATING_COLORS } from "./model.js";

export const VIEWBOX = { width: 1000, height: 500 };

const curves = [
  [[510, 90], [593.33, 90], [676.67, 90], [760, 90]],
  [[760, 90], [850, 90], [900, 125], [900, 200]],
  [[900, 200], [900, 228.33], [900, 256.67], [900, 285]],
  [[900, 285], [900, 355], [865, 395], [790, 395]],
  [[790, 395], [630, 395], [470, 395], [310, 395]],
  [[310, 395], [230, 395], [195, 360], [175, 300]],
  [[175, 300], [140, 235], [145, 185], [200, 158]],
  [[200, 158], [240, 140], [285, 150], [320, 145]],
  [[320, 145], [360, 140], [375, 90], [510, 90]],
];

export const CENTERLINE = curves.flatMap(([a, b, c, d]) =>
  Array.from({ length: 12 }, (_, index) => {
    const t = index / 12;
    const u = 1 - t;
    return {
      x: u ** 3 * a[0] + 3 * u ** 2 * t * b[0] + 3 * u * t ** 2 * c[0] + t ** 3 * d[0],
      y: u ** 3 * a[1] + 3 * u ** 2 * t * b[1] + 3 * u * t ** 2 * c[1] + t ** 3 * d[1],
    };
  }));

const segments = CENTERLINE.map((start, index) => {
  const end = CENTERLINE[(index + 1) % CENTERLINE.length];
  return { start, end, length: Math.hypot(end.x - start.x, end.y - start.y) };
});
export const TRACK_LENGTH = segments.reduce((sum, segment) => sum + segment.length, 0);

export function pointAtFraction(fraction) {
  let distance = ((fraction % 1 + 1) % 1) * TRACK_LENGTH;
  for (const { start, end, length } of segments) {
    if (distance <= length) {
      const amount = distance / length;
      return { x: start.x + (end.x - start.x) * amount, y: start.y + (end.y - start.y) * amount };
    }
    distance -= length;
  }
  return CENTERLINE[0];
}

export function fitCircuit(width, height) {
  const header = 28;
  const footer = 66;
  const padding = 16;
  const availableWidth = Math.max(0, width - padding * 2);
  const availableHeight = Math.max(0, height - header - footer - padding * 2);
  const scale = Math.min(availableWidth / VIEWBOX.width, availableHeight / VIEWBOX.height);
  return {
    scale,
    width: VIEWBOX.width * scale,
    height: VIEWBOX.height * scale,
    left: (width - VIEWBOX.width * scale) / 2,
    top: header + padding + (availableHeight - VIEWBOX.height * scale) / 2,
  };
}

export default class Racetrack extends View {
  init(_props, cx) {
    this.assetRoot = props()?.assetRoot ?? "mods/racetrack";
    this.snapshotText = null;
    this.readVersion = 0;
    this.watchRunning = false;
    this.size = { width: 1000, height: 600 };
    this.directory = home() + "/.pitwall";
    cx.spawn(async (cx) => this.reload(cx));
    this.startWatcher(cx);
    cx.timer.every(60000, (cx) => {
      cx.spawn(async (cx) => this.reload(cx));
      this.startWatcher(cx);
      cx.notify();
    });
  }

  async reload(cx) {
    const version = ++this.readVersion;
    let text = null;
    try { text = await readTextFile(this.directory + "/state.json"); } catch {}
    if (version !== this.readVersion) return;
    this.snapshotText = text;
    cx.notify();
  }

  startWatcher(cx) {
    if (this.watchRunning) return;
    this.watchRunning = true;
    cx.spawn(async (cx) => {
      for (;;) {
        try { await watchFolder(this.directory); }
        catch { this.watchRunning = false; break; }
        await this.reload(cx);
      }
      cx.notify();
    });
  }

  render() {
    const t = theme();
    const bounds = fitCircuit(this.size.width, this.size.height);
    const s = bounds.scale;
    const assetRoot = this.assetRoot ?? "mods/racetrack";
    const model = race(this.snapshotText, agents().map((agent) => ({
      key: agent.address, programKey: agent.program.key, programName: agent.program.name,
      spaceName: agent.space_name, status: agent.status,
    })), Date.now());
    const flagColor = ({ yellow: t.ansi3, red: t.ansi1, green: t.ansi2 })[model.flag] ?? t.foreground;
    const focus = (terminal) => { if (terminal !== null) run("agent.focus", { terminal }); };
    const carArt = (car) => {
      const details = car.driver === "codex" ? "car-codex-details.svg" :
        car.driver === "glm-flash" ? "car-flash-details.svg" : "car-details.svg";
      return div().relative().w(44 * s).h(26 * s)
        .child(svg(`${assetRoot}/car-body.svg`).absolute().left(0).top(0).w(44 * s).h(26 * s)
          .text_color(car.livery ?? t.muted))
        .child(image(`${assetRoot}/${details}`).absolute().left(0).top(0).w(44 * s).h(26 * s))
        .when(car.tyreColor !== null, (el) => el.child(div().absolute().left(11 * s).top(1 * s)
          .w(5 * s).h(5 * s).rounded_full().bg(car.tyreColor)));
    };
    const finished = model.cars.filter((car) => car.mode === "finished");
    const labels = [
      [539, 37, "START / FINISH", 11, t.muted],
      [713, 149, "01", 12, t.dim], [816, 321, "02", 12, t.dim], [183, 359, "03", 12, t.dim],
      [256, 232, "GARAGE", 14, t.foreground], [433, 272, "PIT BOXES", 10, t.muted],
      [520, 350, "PIT LANE", 10, t.muted], [433, 219, "PIT WALL", 28, t.foreground],
      [434, 251, "ELAPSED TIME / PACE", 10, t.dim],
    ];
    return div().id("racetrack-root").relative().size_full().overflow_hidden()
      .bg(t.background).text_color(t.foreground)
      .on_size_change((size, cx) => {
        if (size.width === this.size.width && size.height === this.size.height) return;
        this.size = size;
        cx.notify();
      })
      .child(h_flex().absolute().left(0).top(0).w_full().h(28).px(14).gap(10)
        .items_center().bg(t.chrome).border_b(1).border_color(t.border)
        .child(div().w(4).h(12).bg(flagColor))
        .child(div().font_bold().text_size(10).text_color(flagColor)
          .child(model.flag === "chequered" ? "▦ CHEQUERED" : (model.flag ?? "NO DATA").toUpperCase()))
        .child(div().flex_1().text_size(10).text_color(t.muted).child("RACE CONTROL"))
        .child(div().font_semibold().text_size(10).text_color(t.muted)
          .child(`FASTEST PIT TODAY ${model.fastestPitMinutes === null ? "-" : model.fastestPitMinutes.toFixed(1) + "m"}`)))
      .child(div().absolute().left(bounds.left).top(bounds.top).w(bounds.width).h(bounds.height)
        .child(image(`${assetRoot}/track.svg`).absolute().left(0).top(0).w(bounds.width).h(bounds.height))
        .children(labels.map(([x, y, label, fontSize, color]) =>
          div().absolute().left(x * s).top(y * s).text_size(fontSize * s)
            .font_semibold().text_color(color).child(label)))
        .children(Array.from({ length: 6 }, (_, bay) => div().id(`pit-bay-${bay}`).absolute()
          .left((433 + bay * 48) * s).top(291 * s).w(40 * s).h(30 * s)
          .when(model.cars.some((car) => car.mode === "pit" && car.bay === bay), (el) =>
            el.border(2).border_color(t.blocked).loop("opacity", { from: 0.4, to: 1, period: 1800 }))
          .child(div().absolute().left(15 * s).top(32 * s).text_size(9 * s).text_color(t.muted)
            .child(String(bay + 1).padStart(2, "0")))))
        .children(model.garage.map((agent, index) => div().id(`garage-${agent.key}`).absolute()
          .left((243 + (index % 2) * 75) * s).top((270 + Math.floor(index / 2) * 39) * s)
          .w(Math.max(45, 42 * s)).h(Math.max(34, 34 * s)).on_click(() => focus(agent.key))
          .child(div().w(17 * s).h(10 * s).rounded(3 * s).bg(t[agent.status] ?? t.muted))
          .child(div().text_size(9).text_color(t.muted).child(agent.programName ?? agent.programKey))))
        .children(model.cars.map((car, index) => {
          const point = car.mode === "track" ? pointAtFraction(car.fraction) :
            car.mode === "pit" ? { x: 453 + car.bay * 48, y: 306 - car.stack * 44 } :
              { x: 510 + (finished.indexOf(car) % 4) * 60,
                y: 90 + Math.floor(finished.indexOf(car) / 4) * 50 };
          const labelColor = car.mode === "finished" ? RATING_COLORS[car.rating] : t.foreground;
          return div().id(`car-${car.key}`).absolute()
            .left((point.x - 22) * s).top((point.y - 13) * s).w(Math.max(120, 110 * s)).h(Math.max(48, 46 * s))
            .transition("left", { duration: 1200, easing: "linear" })
            .transition("top", { duration: 1200, easing: "linear" })
            .on_click(() => focus(car.terminal))
            .when(car.mode === "pit", (el) => el.loop("opacity", { from: 0.5, to: 1, period: 1800 }))
            .child(carArt(car))
            .child(h_flex().mt((index % 3) * 12).gap(3 * s).items_center()
              .child(div().max_w(120).truncate().text_size(9).font_semibold()
                .text_color(labelColor).child(car.title))
              .when(car.mode !== "finished" && car.completedLaps > 0, (el) =>
                el.child(div().text_size(9).text_color("#eab308").child(`+${car.completedLaps}`))))
            .when(car.mode === "pit", (el) => el.child(div().text_size(9)
              .text_color(t.blocked).child(`${car.waitingMinutes}m waiting`)))
            .when(car.mode === "finished", (el) => el.child(div().text_size(9)
              .text_color(labelColor).child(`${car.hours.toFixed(2)}h`)));
        })))
      .child(v_flex().absolute().left(16).top(Math.max(28, this.size.height - 56))
        .w(Math.max(0, this.size.width - 32)).gap(5).text_size(10)
        .child(div().text_color(t.muted).child(model.data === "no-data" ? "Race data unavailable" :
          `${model.cars.filter((car) => car.mode === "track").length} ON TRACK · ${model.cars.filter((car) => car.mode === "pit").length} IN PIT · ${model.garage.length} IN GARAGE`))
        .child(div().text_color(t.dim).child("Clock position is elapsed time, not progress. Click a linked car or garage icon for onboard.")));
  }
}
