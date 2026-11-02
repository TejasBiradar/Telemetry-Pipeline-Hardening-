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
    s.addText("Driftline keeps three things for a pipeline", { placeholder: "title" });
    const steps = [
      ["Stages from the code", "Python or SQL is read into a code graph. Each stage has a file and a line."],
      ["Guarantees a person confirmed", "Only those rules are watched. Pass and fail stay deterministic."],
      ["A connector for the stage output", "MinIO or Postgres, saved on that pipeline. Each new stage is read from there, and the result is stored."],
    ];
    steps.forEach((item, i) => {
      const x = 0.55 + i * 4.2;
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
        x, y: 1.35, w: 3.95, h: 4.55,
        fill: { color: SOFT }, rectRadius: 0.1, shadow: shadow(), objectName: `step-${i}`,
      });
      s.addText(item[0], {
        x: x + 0.28, y: 1.6, w: 3.4, h: 1.15,
        fontFace: "Cambria", fontSize: 22, bold: true, color: INK, margin: 0, isTextBox: true,
      });
      s.addText(item[1], {
        x: x + 0.28, y: 2.95, w: 3.4, h: 2.5,
        fontFace: "Calibri", fontSize: 18, color: INK, margin: 0, isTextBox: true,
      });
    });
    s.addText("Their job still writes the stage. Driftline records what it found.", {
      x: 0.55, y: 6.15, w: 12.2, h: 0.4,
      fontFace: "Calibri", fontSize: 16, color: MUTED, margin: 0, isTextBox: true,
    });
    s.addNotes("This slide names what the product holds. The next slides show how it is built and the order of a run. Demo: Source, the code graph, then the connector.");
  }

  // 3 — Architecture
  pres.addSection({ title: "Architecture" });
  {
    const s = pres.addSlide({ masterName: "light", sectionTitle: "Architecture" });
    s.addText("Driftline sits beside their pipeline", { placeholder: "title" });

    s.addText("THEIR PIPELINE", {
      x: 0.55, y: 1.12, w: 4, h: 0.28,
      fontFace: "Calibri", fontSize: 12, bold: true, color: MUTED, margin: 0, charSpacing: 1.1, isTextBox: true,
    });
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x: 0.55, y: 1.48, w: 5.35, h: 1.55,
      fill: { color: SOFT }, rectRadius: 0.1, objectName: "arch-code",
    });
    s.addText("Python or SQL", {
      x: 0.75, y: 1.62, w: 4.95, h: 0.38,
      fontFace: "Cambria", fontSize: 18, bold: true, color: INK, margin: 0, isTextBox: true,
    });
    s.addText("Their scheduler still runs the pipeline. Driftline does not replace it.", {
      x: 0.75, y: 2.08, w: 4.95, h: 0.7,
      fontFace: "Calibri", fontSize: 15, color: INK, margin: 0, isTextBox: true,
    });
    s.addShape(pres.shapes.RIGHT_ARROW, {
      x: 6.05, y: 2.08, w: 0.42, h: 0.28,
      fill: { color: TEAL }, objectName: "arch-arrow-out",
    });
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x: 6.62, y: 1.48, w: 6.15, h: 1.55,
      fill: { color: "E7F3F1" }, rectRadius: 0.1, objectName: "arch-store",
    });
    s.addText("Stage output", {
      x: 6.82, y: 1.62, w: 5.75, h: 0.38,
      fontFace: "Cambria", fontSize: 18, bold: true, color: TEAL_DEEP, margin: 0, isTextBox: true,
    });
    s.addText("MinIO folder or Postgres table, one place per stage. Named on the connector.", {
      x: 6.82, y: 2.08, w: 5.75, h: 0.7,
      fontFace: "Calibri", fontSize: 15, color: INK, margin: 0, isTextBox: true,
    });

    s.addShape(pres.shapes.DOWN_ARROW, {
      x: 9.35, y: 3.15, w: 0.32, h: 0.36,
      fill: { color: TEAL }, objectName: "arch-arrow-down",
    });

    s.addText("HOSTED DRIFTLINE", {
      x: 0.55, y: 3.58, w: 5, h: 0.28,
      fontFace: "Calibri", fontSize: 12, bold: true, color: MUTED, margin: 0, charSpacing: 1.1, isTextBox: true,
    });
    const flow = [
      ["Register", "Git URL or folder. The clone is analyzed, then deleted."],
      ["Code graph", "Stages, fields, and proposed guarantees, with file and line."],
      ["Confirm", "A person chooses which stages and guarantees to watch."],
      ["Read", "The connector opens the stage output they named."],
      ["Results", "Pass or fail is stored in Postgres and shown in the app."],
    ];
    flow.forEach((item, i) => {
      const x = 0.55 + i * 2.52;
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
        x, y: 3.98, w: 2.22, h: 2.55,
        fill: { color: i === 4 ? "E7F3F1" : SOFT }, rectRadius: 0.08, objectName: `arch-step-${i}`,
      });
      s.addText(String(i + 1), {
        x: x + 0.12, y: 4.1, w: 1.95, h: 0.32,
        fontFace: "Cambria", fontSize: 14, bold: true, color: TEAL, margin: 0, isTextBox: true,
      });
      s.addText(item[0], {
        x: x + 0.12, y: 4.42, w: 1.95, h: 0.55,
        fontFace: "Cambria", fontSize: 16, bold: true, color: INK, margin: 0, isTextBox: true,
      });
      s.addText(item[1], {
        x: x + 0.12, y: 5.05, w: 1.95, h: 1.3,
        fontFace: "Calibri", fontSize: 13, color: INK, margin: 0, isTextBox: true,
      });
      if (i < flow.length - 1) {
        s.addShape(pres.shapes.RIGHT_ARROW, {
          x: x + 2.24, y: 5.1, w: 0.24, h: 0.18,
          fill: { color: TEAL }, objectName: `arch-flow-${i}`,
        });
      }
    });
    s.addNotes("Walk the diagram top to bottom, then left to right. Their pipeline writes the stage. Driftline only reads it through the connector. Do not quote precision or recall. If asked how a guarantee is trusted: it has a file and a line, and a person confirms it.");
  }

  // Tech stack, between architecture and lifecycle
  pres.addSection({ title: "Tech stack" });
  {
    const s = pres.addSlide({ masterName: "light", sectionTitle: "Tech stack" });
    s.addText("What the hosted app is built on", { placeholder: "title" });
    const stack = [
      ["Web", "React", "Source, code graph, stages, guarantees, and results."],
      ["API", "FastAPI", "Registration, confirmation, and the connector save."],
      ["Analysis", "Python, sqlglot, networkx", "Python and SQL become stages, fields, and guarantees."],
      ["Watcher", "Python", "Reads each stage and runs the checks."],
      ["Record", "PostgreSQL", "Pipelines, stages, guarantees, and pass or fail."],
      ["Stage output", "MinIO or Postgres", "Where their pipeline writes the stage the connector reads."],
    ];
    stack.forEach((item, i) => {
      const col = i % 3;
      const row = Math.floor(i / 3);
      const x = 0.55 + col * 4.2;
      const y = 1.35 + row * 2.7;
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
        x, y, w: 3.95, h: 2.45,
        fill: { color: row === 1 ? "E7F3F1" : SOFT }, rectRadius: 0.1, objectName: `stack-${i}`,
      });
      s.addText(item[0], {
        x: x + 0.24, y: y + 0.22, w: 3.45, h: 0.36,
        fontFace: "Calibri", fontSize: 13, bold: true, color: MUTED, margin: 0, isTextBox: true,
      });
      s.addText(item[1], {
        x: x + 0.24, y: y + 0.62, w: 3.45, h: 0.7,
        fontFace: "Cambria", fontSize: 18, bold: true, color: INK, margin: 0, isTextBox: true,
      });
      s.addText(item[2], {
        x: x + 0.24, y: y + 1.4, w: 3.45, h: 0.8,
        fontFace: "Calibri", fontSize: 15, color: INK, margin: 0, isTextBox: true,
      });
    });
    s.addNotes("Name the stack after the diagram. React and FastAPI are the hosted app. sqlglot and networkx build the code graph. Postgres stores the record. MinIO or Postgres is where their pipeline writes the stage.");
  }

  // 4 — Lifecycle
  pres.addSection({ title: "Lifecycle" });
  {
    const s = pres.addSlide({ masterName: "light", sectionTitle: "Lifecycle" });
    s.addText("Life of a pipeline", { placeholder: "title" });

    s.addText("ONCE", {
      x: 0.55, y: 1.12, w: 3, h: 0.28,
      fontFace: "Calibri", fontSize: 12, bold: true, color: MUTED, margin: 0, charSpacing: 1.1, isTextBox: true,
    });
    const once = [
      ["Register", "Point at the Python or SQL source. Analysis keeps the stages and drops the clone."],
      ["Confirm", "A person accepts the stages and the guarantees to watch."],
      ["Connect", "Save MinIO or Postgres, and the place where each stage lands."],
    ];
    once.forEach((item, i) => {
      const x = 0.55 + i * 4.2;
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
        x, y: 1.48, w: 3.95, h: 1.85,
        fill: { color: SOFT }, rectRadius: 0.1, objectName: `life-once-${i}`,
      });
      s.addText(item[0], {
        x: x + 0.22, y: 1.62, w: 3.5, h: 0.4,
        fontFace: "Cambria", fontSize: 18, bold: true, color: INK, margin: 0, isTextBox: true,
      });
      s.addText(item[1], {
        x: x + 0.22, y: 2.1, w: 3.5, h: 1.0,
        fontFace: "Calibri", fontSize: 15, color: INK, margin: 0, isTextBox: true,
      });
    });

    s.addText("EVERY RUN", {
      x: 0.55, y: 3.58, w: 4, h: 0.28,
      fontFace: "Calibri", fontSize: 12, bold: true, color: MUTED, margin: 0, charSpacing: 1.1, isTextBox: true,
    });
    const eachRun = [
      ["Write", "Their job writes the stage to the place named on the connector."],
      ["Read", "Driftline opens that stage when it appears."],
      ["Check", "Volume, missing fields, and nulls on a required field."],
      ["Show", "Pass or fail is stored and shown on that pipeline."],
    ];
    eachRun.forEach((item, i) => {
      const x = 0.55 + i * 3.13;
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
        x, y: 3.96, w: 2.88, h: 2.0,
        fill: { color: "E7F3F1" }, rectRadius: 0.1, objectName: `life-run-${i}`,
      });
      s.addText(item[0], {
        x: x + 0.16, y: 4.08, w: 2.56, h: 0.38,
        fontFace: "Cambria", fontSize: 18, bold: true, color: TEAL_DEEP, margin: 0, isTextBox: true,
      });
      s.addText(item[1], {
        x: x + 0.16, y: 4.52, w: 2.56, h: 1.25,
        fontFace: "Calibri", fontSize: 14, color: INK, margin: 0, isTextBox: true,
      });
    });
    s.addText("The next batch starts again at Write.", {
      x: 0.55, y: 6.22, w: 12, h: 0.36,
      fontFace: "Calibri", fontSize: 15, color: MUTED, margin: 0, isTextBox: true,
    });
    s.addNotes("Setup is once: register, confirm, connect. After that, every time their job writes a stage, Driftline reads it, checks it, and shows the result. Then the next batch starts at Write again.");
  }

  // 5 — What it captures and flags
  pres.addSection({ title: "What it catches" });
  {
    const s = pres.addSlide({ masterName: "light", sectionTitle: "What it catches" });
    s.addText("The stage, the field, and the flag", { placeholder: "title" });
    const cards = [
      ["Captures", "The stage that just landed, the fields the code graph named, and the guarantees a person confirmed."],
      ["Flags", "An empty stage. A confirmed field that is missing. A required field that arrived null."],
      ["Helps", "The owner sees the stage and the field in the same run, while the dashboard still looks fine."],
    ];
    cards.forEach((item, i) => {
      const x = 0.55 + i * 4.2;
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
        x, y: 1.4, w: 3.95, h: 5.15,
        fill: { color: i === 1 ? "E7F3F1" : SOFT }, rectRadius: 0.1, shadow: shadow(), objectName: `catch-${i}`,
      });
      s.addText(item[0], {
        x: x + 0.28, y: 1.7, w: 3.4, h: 0.6,
        fontFace: "Cambria", fontSize: 26, bold: true, color: i === 1 ? TEAL_DEEP : INK, margin: 0, isTextBox: true,
      });
      s.addText(item[1], {
        x: x + 0.28, y: 2.6, w: 3.4, h: 3.4,
        fontFace: "Calibri", fontSize: 18, color: INK, margin: 0, isTextBox: true,
      });
    });
    s.addNotes("These are the checks the watcher runs today: volume, schema, and nulls on a required field. Do not add unit or row-filter flags. Show Results on the live app after a trigger if a run is already there.");
  }

  // 5 — Conclusion
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
      ["How this helps", "It keeps the stage that landed, the fields from the code graph, and the guarantees a person confirmed. It flags an empty stage, a missing confirmed field, and a required field that arrived null. The owner sees the stage and the field in the same run."],
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
        fontFace: "Cambria", fontSize: 22, bold: true, color: "7DCEC4", margin: 0, isTextBox: true,
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

  const out = "/home/smita/work/Telemetry-Pipeline-Hardening-/docs/driftline-panel-deck-conclusion.pptx";
  await pres.writeFile({ fileName: out });
  await applyTheme(out, THEME);
  console.log(out);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
