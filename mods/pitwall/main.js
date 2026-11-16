import { View, div } from "gpui-kit";
import { h_flex, v_flex } from "gpui-base";
import { agents, theme, home, readTextFile, watchFolder } from "herdr";
import { tower } from "./model.js";

export default class Pitwall extends View {
  init(_props, cx) {
    this.snapshotText = null;
    this.readVersion = 0;
    this.watchRunning = false;
    this.directory = home() + "/.pitwall";
    cx.spawn(async (cx) => this.reload(cx));
    this.startWatcher(cx);
    cx.timer.every(30000, (cx) => {
      cx.spawn(async (cx) => this.reload(cx));
      this.startWatcher(cx);
    });
  }

  async reload(cx) {
    const version = ++this.readVersion;
    let text = null;
    try {
      text = await readTextFile(this.directory + "/state.json");
    } catch {}
    if (version !== this.readVersion) return;
    this.snapshotText = text;
    cx.notify();
  }

  startWatcher(cx) {
    if (this.watchRunning) return;
    this.watchRunning = true;
    cx.spawn(async (cx) => {
      for (;;) {
        try {
          await watchFolder(this.directory);
        } catch {
          this.watchRunning = false;
          break;
        }
        await this.reload(cx);
      }
      cx.notify();
    });
  }

  render() {
    const t = theme();
    const model = tower(this.snapshotText, agents().map((agent) => ({
      key: agent.address,
      programName: agent.program.name,
      spaceName: agent.space_name,
      status: agent.status,
    })), Date.now());
    const section = (name, body = []) => v_flex().flex_none().min_w(0).px(16).py(8).gap(6)
      .border_t(1).border_color(t.border)
      .child(div().font_semibold().text_size(10).text_color(t.dim).child(name))
      .children(body);
    const quiet = (text) => div().text_size(11).text_color(t.dim).child(text);
    const hours = (value) => value === null ? "-" : `${value.toFixed(1)}h`;
    const grouped = (value) => value.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
    const count = (value) => value == null ? "-" : grouped(String(value));
    const dollars = (value) => value == null ? "-" : `$${grouped(value.toFixed(2))}`;
    const metric = (label, value) => h_flex().items_center().justify_between().gap(12)
      .child(div().flex_none().text_size(10).text_color(t.muted).child(label))
      .child(div().flex_none().font_semibold().child(value));
    const fuel = model.fuel;
    const garageColumns = [["CI", "ci", 22], ["TEST", "tests", 32],
      ["README", "readme", 44], ["ACTIVE", "active", 40]];

    return v_flex().id("pitwall-tower").size_full().min_h(0).overflow_y_scrollbar()
      .bg(t.chrome).text_color(t.foreground).text_size(12)
      .child(v_flex().flex_none().px(16).py(12).gap(7)
        .child(h_flex().items_center().gap(9)
          .child(div().w(3).h(20).bg(t.accent))
          .child(div().flex_1().font_bold().text_size(18).child("PIT WALL"))
          .child(div().px(8).py(4).rounded(3).bg(t.raised).font_semibold().text_size(10)
            .text_color(model.openCount > 0 ? t.blocked : t.muted)
            .child(`IN PIT ${model.openCount ?? "-"}`)))
        .when(model.data === "no-data", (el) => el.child(quiet("NO DATA"))))
      .child(section("GRID", model.grid.length ? model.grid.map((agent) =>
        h_flex().id(`grid-${agent.key}`).items_center().gap(8).py(3)
          .child(div().w(22).flex_none().text_color(t.dim).child(String(agent.position).padStart(2, "0")))
          .child(div().flex_1().min_w(0).font_semibold().truncate().child(agent.programName))
          .child(div().w(84).flex_none().truncate().text_size(10).text_color(t.muted).child(agent.spaceName))
          .child(div().w(54).flex_none().text_size(9).text_color(t[agent.status]).child(agent.status.toUpperCase())))
        : [quiet("No agents")]))
      .child(section("IN PIT", model.data === "no-data" ? [quiet("NO DATA")]
        : model.asks.length ? model.asks.map((ask) =>
          v_flex().id(`ask-${ask.key}`).gap(6).pl(9).py(7).border_l(2)
            .border_color(ask.overdue ? t.blocked : t.accent)
            .text_color(ask.overdue ? t.blocked : t.foreground)
            .loop("opacity", { from: 0.65, to: 1, period: 3600 })
            .child(h_flex().gap(8).items_center()
              .child(div().w(48).flex_none().text_size(9).font_semibold().child(ask.type.toUpperCase()))
              .child(div().flex_1().min_w(0).font_semibold().truncate().child(ask.headline)))
            .child(h_flex().gap(7).items_center().text_size(10)
              .text_color(ask.overdue ? t.blocked : t.muted)
              .child(div().flex_1().min_w(0).truncate().child(`${ask.project} / ${ask.agent}`))
              .child(div().flex_none().child(`${ask.waitingMinutes}m`))))
          : [quiet("Clear")]))
      .child(section("SECTORS", model.sectors.map((sector) =>
        h_flex().id(`sector-${sector.label}`).items_center().gap(12)
          .child(div().w(48).flex_none().text_size(10).text_color(t.muted).child(sector.label))
          .child(div().w(100).h(4).flex_none().rounded(2).bg(t.raised)
            .child(div().w(sector.value ?? 0).h(4).rounded(2).bg(t.accent)))
          .child(h_flex().flex_1().justify_end().text_size(11).child(sector.value === null ? "-" : String(sector.value))))))
      .child(section("LAPS", model.data === "no-data" ? [quiet("NO DATA")] : [
        ...model.laps.map((lap) => h_flex().id(`lap-${lap.key}`).items_center().gap(8)
          .child(div().flex_1().min_w(0).truncate().child(lap.title))
          .child(div().flex_none().text_color(t.working).child(hours(lap.elapsedHours)))),
        h_flex().gap(20).pt(3).text_size(10)
          .children([["LAST", model.lastHours], ["BEST", model.bestHours]].map(([label, value]) =>
            h_flex().flex_1().justify_between().gap(8)
              .child(div().text_color(t.dim).child(label))
              .child(div().text_color(t.muted).child(hours(value))))),
      ]))
      .child(section("FUEL", [
        metric("TOKENS TODAY", count(fuel?.tokens_today)),
        metric("TOKENS 7D", count(fuel?.tokens_7d)),
        metric("PAID", fuel === null ? "-" : `${dollars(fuel.out_of_pocket_month_usd)}/mo`),
        metric("VALUE", dollars(fuel?.api_value_30d_usd)),
        quiet("30d, API-equivalent"),
        metric("RATIO", fuel?.value_ratio == null ? "-" : `${fuel.value_ratio.toFixed(2)}x`),
      ]))
      .child(section("GARAGE", model.garage.length ? [
        h_flex().gap(5).items_center().text_size(9).text_color(t.dim)
          .child(div().flex_1().min_w(0).child("PROJECT"))
          .children(garageColumns.map(([label, , width]) =>
            div().w(width).flex_none().text_center().child(label)))
          .child(div().w(26).flex_none().text_right().child("7D")),
        ...model.garage.map((row, index) => h_flex().id(`garage-${index}`).gap(5).items_center().text_size(11)
          .child(div().flex_1().min_w(0).whitespace_normal().child(row.project))
          .children(garageColumns.map(([, key, width]) => div().w(width).flex_none().text_center()
            .text_color(row[key] ? t.working : t.blocked).child(row[key] ? "✓" : "✗")))
          .child(div().w(26).flex_none().text_right().child(String(row.commits_7d)))),
      ] : [quiet("No project health")]))
      .child(section("RADIO", model.radio === null ? [quiet("No coach note")] : [
        quiet(model.radio.date),
        div().flex_none().min_w(0).whitespace_normal().text_size(11).line_height(1.3)
          .child(`Observation: ${model.radio.observation}`),
        div().flex_none().min_w(0).whitespace_normal().text_size(11).line_height(1.3)
          .child(`Tweak: ${model.radio.tweak}`),
      ]));
  }
}
