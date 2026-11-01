const pptxgen = require("pptxgenjs");
const { applyTheme } = require("/home/smita/.claude/skills/synced/d03ce216-2ca2-4381-b28f-79a245d6c206_52fcd0d2-7448-4855-ab3a-fd3288d734ac/pptx/scripts/apply_theme.js");

const THEME = {
  name: "Driftline",
  headFontFace: "Cambria",
  bodyFontFace: "Calibri",
  colors: {
    dk1: "14201C",
    lt1: "FFFFFF",
    dk2: "0B5F58",
    lt2: "E8EEEC",
    accent1: "0F766E",
    accent2: "B45309",
    accent3: "047857",
    accent4: "B91C1C",
    accent5: "5A6B65",
    accent6: "1C3A36",
    hlink: "0F766E",
    folHlink: "B45309",
  },
};

const INK = "14201C";
const PAPER = "FFFFFF";
const MIST = "E8EEEC";
const TEAL = "0F766E";
const TEAL_DEEP = "0B5F58";
const AMBER = "B45309";
const GREEN = "047857";
const MUTED = "5A6B65";
const SOFT = "F4F7F6";

function shadow() {
  return { type: "outer", color: "14201C", blur: 10, opacity: 0.08, offset: 3, angle: 90 };
}

async function main() {
  const pres = new pptxgen();
  pres.defineLayout({ name: "WIDE", width: 13.333, height: 7.5 });
  pres.layout = "WIDE";
  pres.title = "Driftline — Brief 31";
  pres.author = "Driftline";
  pres.subject = "Panel deck for the live demonstration";
  pres.theme = { headFontFace: "Cambria", bodyFontFace: "Calibri" };

  pres.defineSlideMaster({
    title: "light",
    background: { color: PAPER },
    objects: [
      {
        placeholder: {
          options: {
            name: "title", type: "title",
            x: 0.55, y: 0.32, w: 12.2, h: 0.62,
            fontFace: "Cambria", fontSize: 32, bold: true, color: INK, margin: 0,
          },
        },
      },
      {
        text: {
          text: "Driftline  ·  Brief #31",
          options: { x: 0.55, y: 7.05, w: 6.5, h: 0.28, fontFace: "Calibri", fontSize: 12, color: MUTED, margin: 0 },
        },
      },
    ],
    slideNumber: { x: 12.15, y: 7.05, w: 0.6, h: 0.28, fontFace: "Calibri", fontSize: 12, color: MUTED },
  });

  pres.defineSlideMaster({
    title: "dark",
    background: { color: INK },
    objects: [
      {
        text: {
          text: "Driftline  ·  Brief #31",
          options: { x: 0.55, y: 7.05, w: 6.5, h: 0.28, fontFace: "Calibri", fontSize: 12, color: "9AADA6", margin: 0 },
        },
      },
    ],
    slideNumber: { x: 12.15, y: 7.05, w: 0.6, h: 0.28, fontFace: "Calibri", fontSize: 12, color: "9AADA6" },
  });

  // 1 — Problem
  pres.addSection({ title: "Problem" });
  {
    const s = pres.addSlide({ masterName: "dark", sectionTitle: "Problem" });
    s.addText("THE BRIEF", {
      x: 0.55, y: 0.42, w: 4, h: 0.28,
      fontFace: "Calibri", fontSize: 13, bold: true, color: "7DCEC4",
      margin: 0, charSpacing: 1.4, isTextBox: true,
    });
    s.addText("The dashboard stays up.\nThe data is already wrong.", {
      x: 0.55, y: 0.85, w: 11.5, h: 1.7,
      fontFace: "Cambria", fontSize: 40, bold: true, color: PAPER, margin: 0, isTextBox: true,
    });
    s.addText("Event telemetry breaks quietly. Nothing crashes. The wrong number is found weeks later, when a person questions it.", {
      x: 0.55, y: 2.7, w: 10.5, h: 0.7,
      fontFace: "Calibri", fontSize: 18, color: "D5E4E0", margin: 0, isTextBox: true,
    });
    const pains = [
      ["Unit change", "A field is stored in a new unit. Later steps still treat the old one as truth."],
      ["A source goes quiet", "One client version stops sending. The dashboard averages over what remains."],
      ["A field goes nullable", "A value that used to be required arrives empty. Downstream code assumes it is there."],
    ];
    pains.forEach((item, i) => {
      const x = 0.55 + i * 4.2;
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
        x, y: 3.65, w: 3.95, h: 2.85,
        fill: { color: "1C3A36" }, rectRadius: 0.12, objectName: `pain-${i}`,
      });
      s.addText(String(i + 1), {
        x: x + 0.22, y: 3.9, w: 0.5, h: 0.4,
        fontFace: "Cambria", fontSize: 20, bold: true, color: "F2C48D", margin: 0, isTextBox: true,
      });
      s.addText(item[0], {
        x: x + 0.22, y: 4.4, w: 3.5, h: 0.7,
        fontFace: "Cambria", fontSize: 22, bold: true, color: PAPER, margin: 0, isTextBox: true,
      });
      s.addText(item[1], {
        x: x + 0.22, y: 5.2, w: 3.5, h: 1.05,
        fontFace: "Calibri", fontSize: 15, color: "D5E4E0", margin: 0, isTextBox: true,
      });
    });
    s.addNotes("Open on the pain, then go to the live app. Do not walk the architecture yet. The three cards are the brief: unit change, a client version that stops, a newly nullable field. Name who carries it: people reading the dashboard, and the people who own the pipeline and cannot see where it started.");
  }

  // 2 — Solution
  pres.addSection({ title: "Solution" });
  {
    const s = pres.addSlide({ masterName: "light", sectionTitle: "Solution" });
    s.addText("Clients register. Driftline reads the stage.", { placeholder: "title" });
    s.addText("The product is a hosted web app. Nothing is installed beside the client pipeline.", {
      x: 0.55, y: 1.02, w: 12, h: 0.36,
      fontFace: "Calibri", fontSize: 16, color: MUTED, margin: 0, isTextBox: true,
    });
    const steps = [
      ["1", "Register", "A public Git URL or a folder. Python or SQL. The clone is analyzed, then deleted."],
      ["2", "Confirm", "Stages and guarantees come from the code graph. A person confirms them. Checks never use an LLM."],
      ["3", "Connect", "MinIO or Postgres, saved on that pipeline. The watcher reads each stage from there."],
    ];
    steps.forEach((item, i) => {
      const x = 0.55 + i * 4.2;
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
        x, y: 1.52, w: 3.95, h: 2.35,
        fill: { color: SOFT }, rectRadius: 0.1, shadow: shadow(), objectName: `step-${i}`,
      });
      s.addText(item[0], {
        x: x + 0.22, y: 1.74, w: 0.5, h: 0.38,
        fontFace: "Cambria", fontSize: 20, bold: true, color: TEAL, margin: 0, isTextBox: true,
      });
      s.addText(item[1], {
        x: x + 0.7, y: 1.74, w: 2.9, h: 0.38,
        fontFace: "Cambria", fontSize: 22, bold: true, color: INK, margin: 0, isTextBox: true,
      });
      s.addText(item[2], {
        x: x + 0.22, y: 2.28, w: 3.5, h: 1.35,
        fontFace: "Calibri", fontSize: 15, color: INK, margin: 0, isTextBox: true,
      });
    });

    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x: 0.55, y: 4.2, w: 6.05, h: 2.5,
      fill: { color: "E7F3F1" }, rectRadius: 0.1, objectName: "kept",
    });
    s.addText("Kept", {
      x: 0.77, y: 4.38, w: 5.6, h: 0.34,
      fontFace: "Cambria", fontSize: 18, bold: true, color: TEAL_DEEP, margin: 0, isTextBox: true,
    });
    s.addText("Observe by default. Checks run on the data, not on the code. One connector record per pipeline. The supplied pipeline stays read-only.", {
      x: 0.77, y: 4.82, w: 5.55, h: 1.6,
      fontFace: "Calibri", fontSize: 15, color: INK, margin: 0, isTextBox: true,
    });

    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x: 6.85, y: 4.2, w: 5.95, h: 2.5,
      fill: { color: "F8EFE6" }, rectRadius: 0.1, objectName: "rejected",
    });
    s.addText("Rejected", {
      x: 7.07, y: 4.38, w: 5.5, h: 0.34,
      fontFace: "Cambria", fontSize: 18, bold: true, color: AMBER, margin: 0, isTextBox: true,
    });
    s.addText("A client-side install. Treating an Airflow sketch as a pipeline. One shared password for every client. JSON files as the system of record.", {
      x: 7.07, y: 4.82, w: 5.5, h: 1.6,
      fontFace: "Calibri", fontSize: 15, color: INK, margin: 0, isTextBox: true,
    });
    s.addNotes("This is the decision to state out loud: the web app is the product. Demo path after this slide: Source, register the public Git repo, show stages on the graph, then open the connector card. Mention what you will not demo as if it were done: login, and a check for every guarantee kind.");
  }

  // 3 — Methodology
  pres.addSection({ title: "Methodology" });
  {
    const s = pres.addSlide({ masterName: "light", sectionTitle: "Methodology" });
    s.addText("Written down before the agent wrote code", { placeholder: "title" });
    const cols = [
      ["Specify", "BRD from the brief, with open questions left open. ADRs for the core, the data plane, and how a client is onboarded."],
      ["Drive", "The agent works inside CLAUDE.md. It cannot edit the frozen pipeline. It cannot read secrets or the answer key."],
      ["Review", "A person confirms every stage and guarantee. The review log records what the agent produced and the defects caught."],
    ];
    cols.forEach((item, i) => {
      const x = 0.55 + i * 4.15;
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
        x, y: 1.35, w: 3.95, h: 3.35,
        fill: { color: i === 1 ? "E7F3F1" : SOFT }, rectRadius: 0.1, objectName: `method-${i}`,
      });
      s.addText(item[0], {
        x: x + 0.24, y: 1.55, w: 3.45, h: 0.5,
        fontFace: "Cambria", fontSize: 24, bold: true, color: INK, margin: 0, isTextBox: true,
      });
      s.addText(item[1], {
        x: x + 0.24, y: 2.2, w: 3.45, h: 2.15,
        fontFace: "Calibri", fontSize: 16, color: INK, margin: 0, isTextBox: true,
      });
    });
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x: 0.55, y: 4.95, w: 12.25, h: 1.75,
      fill: { color: INK }, rectRadius: 0.1, objectName: "method-rule",
    });
    s.addText("The rule that kept the work honest", {
      x: 0.8, y: 5.15, w: 11.7, h: 0.38,
      fontFace: "Cambria", fontSize: 18, bold: true, color: PAPER, margin: 0, isTextBox: true,
    });
    s.addText("If a claim about the pipeline cannot point at a file and a line, it is not a guarantee. Pass and fail stay deterministic. Odd behaviour is pinned in tests, not “fixed.”", {
      x: 0.8, y: 5.6, w: 11.7, h: 0.8,
      fontFace: "Calibri", fontSize: 16, color: "D5E4E0", margin: 0, isTextBox: true,
    });
    s.addNotes("If asked how the agent was controlled: protected paths, the review log, and human confirm on stages. Do not claim every agent suggestion was accepted. The log records removals, including the MDC config reader.");
  }

  // 4 — Experiment
  pres.addSection({ title: "Experiment" });
  {
    const s = pres.addSlide({ masterName: "light", sectionTitle: "Experiment" });
    s.addText("What failed, and what we changed", { placeholder: "title" });
    const rows = [
      ["Git clone", "The running image had no git. A public repository could not be fetched.", "Git and certificates in the detection image. A real pipeline repo produced five stages."],
      ["Where results live", "Registration was a JSON file. Shipment output was tried in SQLite.", "Postgres holds registration, stages, guarantees, and alerts. Stage tables are Postgres too."],
      ["The connector screen", "One shared environment variable, buried under Advanced settings.", "A connector card per pipeline: MinIO or Postgres, with its own fields."],
      ["A fault that still passes", "Confirmed unit and row-filter guarantees do not all map to a failing check.", "Left visible. The demo must not pretend every injected fault fails today."],
    ];
    rows.forEach((row, i) => {
      const y = 1.15 + i * 1.42;
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
        x: 0.55, y, w: 12.25, h: 1.12,
        fill: { color: i === 3 ? "F8EFE6" : SOFT }, rectRadius: 0.08, objectName: `try-${i}`,
      });
      s.addText(row[0], {
        x: 0.75, y: y + 0.16, w: 2.5, h: 0.94,
        fontFace: "Cambria", fontSize: 16, bold: true, color: i === 3 ? AMBER : TEAL_DEEP, margin: 0, isTextBox: true, valign: "middle",
      });
      s.addText(row[1], {
        x: 3.35, y: y + 0.16, w: 4.4, h: 0.94,
        fontFace: "Calibri", fontSize: 14, color: INK, margin: 0, isTextBox: true, valign: "middle",
      });
      s.addText(row[2], {
        x: 7.9, y: y + 0.16, w: 4.65, h: 0.94,
        fontFace: "Calibri", fontSize: 14, color: INK, margin: 0, isTextBox: true, valign: "middle",
      });
    });
    s.addNotes("Live proof for the first row: the public assignment-data-pipeline repo, subfolder src, entry pipeline.run_pipeline. If you show Shipment Ledger with a fault, say up front that several confirmed guarantee kinds still pass. That is the amber row.");
  }

  // 5 — Results
  pres.addSection({ title: "Results" });
  {
    const s = pres.addSlide({ masterName: "light", sectionTitle: "Results" });
    s.addText("Same faults. Three systems.", { placeholder: "title" });
    s.addText("Web Analytics lab set. Fixed seed. 3,000 events per batch. Recall of injected faults.", {
      x: 0.55, y: 1.05, w: 7.2, h: 0.32,
      fontFace: "Calibri", fontSize: 13, color: MUTED, margin: 0, isTextBox: true,
    });
    s.addChart(pres.charts.BAR, [
      {
        name: "Recall",
        labels: ["B0  no checks", "B1  schema only", "Driftline"],
        values: [0, 0.14, 0.86],
      },
    ], {
      x: 0.4, y: 1.4, w: 7.3, h: 3.45,
      barGrouping: "clustered",
      showValue: true,
      dataLabelPosition: "outEnd",
      dataLabelFontSize: 12,
      dataLabelFontFace: "+mn-lt",
      dataLabelColor: INK,
      chartColors: [TEAL],
      showLegend: false,
      showTitle: false,
      catAxisLabelColor: MUTED,
      catAxisLabelFontSize: 12,
      catAxisLabelFontFace: "+mn-lt",
      valAxisLabelColor: MUTED,
      valAxisLabelFontSize: 12,
      valAxisLabelFontFace: "+mn-lt",
      valAxisMaxValue: 1,
      valAxisMinValue: 0,
      valGridLine: { color: MIST, size: 0.5 },
      catGridLine: { style: "none" },
      chartArea: { fill: { color: PAPER } },
      plotArea: { fill: { color: PAPER } },
      objectName: "recall-chart",
    });

    const stats = [
      ["1.00", "Precision", "Alerts raised were real"],
      ["0", "Lag", "Batches until the first catch"],
      ["0.90", "CI floor", "Recall floor is 0.70"],
    ];
    stats.forEach((item, i) => {
      const y = 1.4 + i * 1.18;
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
        x: 7.9, y, w: 4.85, h: 1.12,
        fill: { color: SOFT }, rectRadius: 0.08, objectName: `stat-${i}`,
      });
      s.addText(item[0], {
        x: 8.1, y: y + 0.14, w: 1.7, h: 0.82,
        fontFace: "Cambria", fontSize: 28, bold: true, color: TEAL, margin: 0, isTextBox: true, valign: "middle",
      });
      s.addText(item[1], {
        x: 9.85, y: y + 0.16, w: 2.7, h: 0.38,
        fontFace: "Cambria", fontSize: 16, bold: true, color: INK, margin: 0, isTextBox: true,
      });
      s.addText(item[2], {
        x: 9.85, y: y + 0.54, w: 2.7, h: 0.4,
        fontFace: "Calibri", fontSize: 13, color: MUTED, margin: 0, isTextBox: true,
      });
    });

    const evidence = [
      ["Security", "Frozen pipeline path. No secrets in the repo. Pass and fail are not an LLM."],
      ["Deployment", "Compose: API, UI, Postgres, MinIO. Health check on /api/health."],
    ];
    evidence.forEach((item, i) => {
      const x = 0.55 + i * 6.35;
      s.addText(item[0], {
        x, y: 5.15, w: 6, h: 0.28,
        fontFace: "Cambria", fontSize: 14, bold: true, color: TEAL_DEEP, margin: 0, isTextBox: true,
      });
      s.addText(item[1], {
        x, y: 5.46, w: 6, h: 0.7,
        fontFace: "Calibri", fontSize: 14, color: INK, margin: 0, isTextBox: true,
      });
    });
    s.addNotes("These numbers are the lab evaluation on Web Analytics, recorded when the gate was set: precision 1.00, recall 0.86, mean lag 0, against B0 recall 0 and B1 recall 0.14. One text fault was missed because the field is sparse. Say the gate floors: precision 0.90, recall 0.70, lag at most 2 batches. Do not quote these numbers for Shipment Ledger.");
  }

  // 6 — Conclusion
  pres.addSection({ title: "Conclusion" });
  {
    const s = pres.addSlide({ masterName: "dark", sectionTitle: "Conclusion" });
    s.addText("From this proof to the product", {
      x: 0.55, y: 0.38, w: 12.2, h: 0.7,
      fontFace: "Cambria", fontSize: 34, bold: true, color: PAPER, margin: 0, isTextBox: true,
    });
    s.addText("The screen you just saw is the product shape. Production is that same registration, with a boundary around each client.", {
      x: 0.55, y: 1.15, w: 12, h: 0.55,
      fontFace: "Calibri", fontSize: 16, color: "D5E4E0", margin: 0, isTextBox: true,
    });
    const cols = [
      ["Still true today", "No client login. A connector secret is stored on the pipeline row. Several confirmed guarantee kinds do not fail a run. Rollback is an image rebuild, not a drilled runbook."],
      ["What production adds", "An account per client. A secret store. A check for every confirmed guarantee. Databricks as a later connector. Profiles so raw files do not have to land here."],
    ];
    cols.forEach((item, i) => {
      const x = 0.55 + i * 6.35;
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
        x, y: 1.95, w: 6.1, h: 3.35,
        fill: { color: "1C3A36" }, rectRadius: 0.12, objectName: `close-${i}`,
      });
      s.addText(item[0], {
        x: x + 0.28, y: 2.15, w: 5.5, h: 0.5,
        fontFace: "Cambria", fontSize: 22, bold: true, color: i === 0 ? "F2C48D" : "7DCEC4", margin: 0, isTextBox: true,
      });
      s.addText(item[1], {
        x: x + 0.28, y: 2.8, w: 5.5, h: 2.15,
        fontFace: "Calibri", fontSize: 16, color: PAPER, margin: 0, isTextBox: true,
      });
    });
    s.addText("We attach beside the pipeline. We do not own their scheduler, and we do not decide pass or fail with a model.", {
      x: 0.55, y: 5.55, w: 12.2, h: 0.7,
      fontFace: "Cambria", fontSize: 18, italic: true, color: "D5E4E0", margin: 0, isTextBox: true,
    });
    s.addNotes("Close on the decision, then take questions. If asked whether Airbyte is required: a connector that we read is enough; Airbyte would only copy data into a database we already read. If asked about Databricks: it is future scope, not a connector on the form. The live demo uses Postgres and MinIO.");
  }

  const out = "/home/smita/work/Telemetry-Pipeline-Hardening-/docs/driftline-panel-deck.pptx";
  await pres.writeFile({ fileName: out });
  await applyTheme(out, THEME);
  console.log(out);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
