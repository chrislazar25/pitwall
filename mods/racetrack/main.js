import { View, div, image } from "gpui-kit";
import { h_flex, v_flex } from "gpui-base";
import { agents, theme, props } from "herdr";

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
    const config = props();
    this.demo = config?.demo === true;
    this.driver = config?.driver === "codex" ? "codex" : "claude";
    this.assetRoot = config?.assetRoot ?? "mods/racetrack";
    this.fraction = 0;
    this.size = { width: 1000, height: 600 };
    if (this.demo) {
      cx.timer.every(2000, (cx) => {
        this.fraction = (this.fraction + 0.02) % 1;
        cx.notify();
      });
    }
  }

  render() {
    const t = theme();
    const bounds = fitCircuit(this.size.width, this.size.height);
    const point = pointAtFraction(this.fraction);
    const s = bounds.scale;
    const labels = [
      [539, 37, "START / FINISH", 11, t.muted],
      [713, 149, "01", 12, t.dim],
      [816, 321, "02", 12, t.dim],
      [183, 359, "03", 12, t.dim],
      [256, 232, "GARAGE", 14, t.foreground],
      [256, 257, "PADDOCK / 06 BAYS", 9, t.muted],
      [433, 272, "PIT BOXES", 10, t.muted],
      [520, 350, "PIT LANE", 10, t.muted],
      [433, 219, "PIT WALL", 28, t.foreground],
      [434, 251, "CIRCUIT STUDY  /  01", 10, t.dim],
    ];
    const observed = agents().map((a) => `${a.program.key} · ${a.program.name} · ${a.address}`);
    const driverName = this.driver === "codex" ? "Codex" : "Claude";
    const car = this.driver === "codex" ? "car-codex.svg" : "car.svg";
    return div().id("racetrack-root").relative().size_full().overflow_hidden()
      .bg(t.background).text_color(t.foreground)
      .on_size_change((size, cx) => {
        if (size.width === this.size.width && size.height === this.size.height) return;
        this.size = size;
        cx.notify();
      })
      .child(h_flex().absolute().left(0).top(0).w_full().h(28).px(14).gap(10)
        .items_center().bg(t.chrome).border_b(1).border_color(t.border)
        .child(div().w(4).h(12).bg("#dc916b"))
        .child(div().font_bold().text_size(10).child(this.demo ? "DEMO" : "CIRCUIT PREVIEW"))
        .child(div().flex_1().text_size(10).text_color(t.muted).child("RACETRACK PROTOTYPE"))
        .child(div().font_semibold().text_size(10).text_color(t.muted)
          .child(this.demo ? `LAP ${String(Math.round(this.fraction * 100)).padStart(2, "0")}%` : "STATIC")))
      .child(div().absolute().left(bounds.left).top(bounds.top).w(bounds.width).h(bounds.height)
        .child(image(`${this.assetRoot}/track.svg`).absolute().left(0).top(0).w(bounds.width).h(bounds.height))
        .children(labels.map(([x, y, label, fontSize, color]) =>
          div().absolute().left(x * s).top(y * s).text_size(fontSize * s)
            .font_semibold().text_color(color).child(label)))
        .children(Array.from({ length: 6 }, (_, i) => div().absolute()
          .left((451 + i * 48) * s).top(303 * s).text_size(10 * s)
          .text_color(t.muted).child(String(i + 1).padStart(2, "0"))))
        .when(this.demo, (el) => el.child(div().id("racetrack-demo-car").absolute()
          .left((point.x - 22) * s).top((point.y - 13) * s).w(44 * s).h(26 * s)
          .transition("left", { duration: 2000, easing: "linear" })
          .transition("top", { duration: 2000, easing: "linear" })
          .child(image(`${this.assetRoot}/${car}`).w(44 * s).h(26 * s)))))
      .child(v_flex().absolute().left(16).top(34)
        .w(Math.max(0, this.size.width - 32)).gap(5).text_size(10)
        .child(h_flex().gap(8).items_center()
          .child(div().w(7).h(7).rounded_full().bg(this.driver === "codex" ? "#6aa5ef" : "#dc916b"))
          .child(div().font_semibold().child(this.demo ? `${driverName} · demo car` : "Static circuit preview"))
          .child(div().flex_1().text_color(t.dim).child(this.demo ? "+2% every 2 seconds · native motion" : "Enable with demo = true")))
        .child(div().text_color(t.dim).child("OBSERVED AGENT PROGRAMS"))
        .child(div().text_color(t.muted).child(observed.length ? observed.join("    /    ") : "No agents observed")));
  }
}
