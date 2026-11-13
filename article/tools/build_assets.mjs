import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";
import { architecture as scientificArchitecture, stateMachine as scientificStateMachine } from "./scientific_schematics.mjs";

const require = createRequire(import.meta.url);
let sharp;
try {
  sharp = require("sharp");
} catch {
  const runtimeRequire = createRequire(
    "C:/Users/warti/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/runtime-entry.cjs",
  );
  sharp = runtimeRequire("sharp");
}

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, "../..");
const DOCS = path.join(ROOT, "docs", "assets");
const ARTICLE = path.join(ROOT, "article", "assets");
fs.mkdirSync(DOCS, { recursive: true });
fs.mkdirSync(ARTICLE, { recursive: true });

const COLORS = {
  ink: "#111111",
  gray: "#5b5b5b",
  light: "#e6e6e6",
  lighter: "#f6f6f6",
  primary: "#1f5a94",
  reserve: "#a34b12",
  ok: "#2f6b3b",
  bad: "#8e2e2e",
};

const esc = (value) => String(value)
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;");

function text(x, y, value, options = {}) {
  const {
    size = 26,
    weight = 400,
    anchor = "start",
    fill = COLORS.ink,
    style = "",
  } = options;
  return `<text x="${x}" y="${y}" font-family="Arial, Helvetica, sans-serif" font-size="${size}" font-weight="${weight}" text-anchor="${anchor}" fill="${fill}" ${style}>${esc(value)}</text>`;
}

function multiline(x, y, lines, options = {}) {
  const { size = 26, lineHeight = Math.round(size * 1.25), anchor = "start", weight = 400, fill = COLORS.ink } = options;
  return `<text x="${x}" y="${y}" font-family="Arial, Helvetica, sans-serif" font-size="${size}" font-weight="${weight}" text-anchor="${anchor}" fill="${fill}">${lines.map((line, i) => `<tspan x="${x}" dy="${i === 0 ? 0 : lineHeight}">${esc(line)}</tspan>`).join("")}</text>`;
}

function svg(width, height, body, title, description) {
  return `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" role="img" aria-labelledby="title desc">
  <title id="title">${esc(title)}</title>
  <desc id="desc">${esc(description)}</desc>
  <rect width="100%" height="100%" fill="#ffffff"/>
  <defs>
    <marker id="arrow-primary" markerWidth="12" markerHeight="12" refX="10" refY="6" orient="auto" markerUnits="strokeWidth"><path d="M0,0 L12,6 L0,12 z" fill="${COLORS.primary}"/></marker>
    <marker id="arrow-reserve" markerWidth="12" markerHeight="12" refX="10" refY="6" orient="auto" markerUnits="strokeWidth"><path d="M0,0 L12,6 L0,12 z" fill="${COLORS.reserve}"/></marker>
    <marker id="arrow-gray" markerWidth="12" markerHeight="12" refX="10" refY="6" orient="auto" markerUnits="strokeWidth"><path d="M0,0 L12,6 L0,12 z" fill="${COLORS.gray}"/></marker>
  </defs>
  ${body}
</svg>`;
}

async function writeSvgAndPng(name, content, width) {
  const svgPath = path.join(DOCS, `${name}.svg`);
  const pngPath = path.join(ARTICLE, `${name}.png`);
  fs.writeFileSync(svgPath, content, "utf8");
  await sharp(Buffer.from(content)).resize({ width }).png({ compressionLevel: 9 }).toFile(pngPath);
}

function architecture(lang) {
  const ru = lang === "ru";
  const L = ru ? {
    title: "Схема испытательного стенда",
    subtitle: "В каждом цикле используется одна аппаратная пара",
    sender: "Активный отправитель",
    receiver: "Приёмник",
    direct: "ESP-NOW: probe и прикладной ACK",
    ap: "Точка доступа 2,4 ГГц",
    udp: "Wi-Fi/UDP: broadcast probe, unicast ACK",
    pc: "Компьютер управления",
    serial: "USB Serial: команды и JSONL-телеметрия",
    pairs: "Испытанные пары: ESP8266–ESP32; ESP8266–ESP32-S3; ESP32–ESP32-S3",
  } : {
    title: "Experimental testbed",
    subtitle: "One hardware pair is active in each controlled cycle",
    sender: "Active sender",
    receiver: "Receiver",
    direct: "ESP-NOW: probe and application ACK",
    ap: "2.4 GHz access point",
    udp: "Wi-Fi/UDP: broadcast probe, unicast ACK",
    pc: "Control computer",
    serial: "USB Serial: commands and JSONL telemetry",
    pairs: "Tested pairs: ESP8266–ESP32; ESP8266–ESP32-S3; ESP32–ESP32-S3",
  };
  const body = [
    text(80, 70, L.title, { size: 38, weight: 700 }),
    text(80, 112, L.subtitle, { size: 24, fill: COLORS.gray }),
    `<rect x="120" y="190" width="460" height="150" fill="#fff" stroke="${COLORS.ink}" stroke-width="3"/>`,
    `<rect x="1020" y="190" width="460" height="150" fill="#fff" stroke="${COLORS.ink}" stroke-width="3"/>`,
    text(350, 250, L.sender, { size: 30, weight: 700, anchor: "middle" }),
    text(350, 294, "ESP8266 / ESP32 / ESP32-S3", { size: 24, anchor: "middle", fill: COLORS.gray }),
    text(1250, 250, L.receiver, { size: 30, weight: 700, anchor: "middle" }),
    text(1250, 294, "ESP8266 / ESP32 / ESP32-S3", { size: 24, anchor: "middle", fill: COLORS.gray }),
    `<line x1="595" y1="235" x2="1005" y2="235" stroke="${COLORS.primary}" stroke-width="6" marker-end="url(#arrow-primary)"/>`,
    `<line x1="1005" y1="295" x2="595" y2="295" stroke="${COLORS.primary}" stroke-width="6" marker-end="url(#arrow-primary)"/>`,
    text(800, 205, L.direct, { size: 23, weight: 700, anchor: "middle", fill: COLORS.primary }),
    `<rect x="570" y="440" width="460" height="125" fill="${COLORS.lighter}" stroke="${COLORS.ink}" stroke-width="3"/>`,
    text(800, 493, L.ap, { size: 29, weight: 700, anchor: "middle" }),
    text(800, 530, "SSID: Lab-2G   •   channel 6", { size: 23, anchor: "middle", fill: COLORS.gray }),
    `<path d="M350 340 L650 430" fill="none" stroke="${COLORS.reserve}" stroke-width="5" stroke-dasharray="13 10" marker-end="url(#arrow-reserve)"/>`,
    `<path d="M1250 340 L950 430" fill="none" stroke="${COLORS.reserve}" stroke-width="5" stroke-dasharray="13 10" marker-end="url(#arrow-reserve)"/>`,
    text(800, 398, L.udp, { size: 22, weight: 700, anchor: "middle", fill: COLORS.reserve }),
    `<rect x="570" y="680" width="460" height="130" fill="#fff" stroke="${COLORS.ink}" stroke-width="3"/>`,
    text(800, 735, L.pc, { size: 29, weight: 700, anchor: "middle" }),
    text(800, 773, "Python GUI + experiment logger", { size: 23, anchor: "middle", fill: COLORS.gray }),
    `<path d="M350 340 L350 745 L555 745" fill="none" stroke="${COLORS.gray}" stroke-width="4" marker-end="url(#arrow-gray)"/>`,
    `<path d="M1250 340 L1250 745 L1045 745" fill="none" stroke="${COLORS.gray}" stroke-width="4" marker-end="url(#arrow-gray)"/>`,
    text(800, 635, L.serial, { size: 22, anchor: "middle", fill: COLORS.gray }),
    `<rect x="120" y="875" width="1360" height="70" fill="${COLORS.lighter}" stroke="${COLORS.light}" stroke-width="2"/>`,
    text(800, 920, L.pairs, { size: 23, anchor: "middle" }),
  ].join("\n");
  return svg(1600, 1000, body, L.title, L.subtitle);
}

function stateMachine(lang) {
  const ru = lang === "ru";
  const L = ru ? {
    title: "Автомат выбора транспорта",
    start: "Запуск",
    stabilize: ["СТАБИЛИЗАЦИЯ", "3 окна без переключения"],
    esp: ["ESP-NOW", "основной транспорт", "probe каждые 470 мс"],
    udp: ["UDP", "резерв через точку доступа", "ESP-NOW probe каждые 940 мс"],
    down: ["потери ≥ 30 %", "2 окна подряд по 5 с"],
    up: ["ACK ≥ 80 %", "3 окна подряд по 5 с"],
    note: "Решение принимается по прикладным ACK. Гистерезис 2/3 окна исключает дребезг около порога.",
  } : {
    title: "Transport selection state machine",
    start: "Start",
    stabilize: ["STABILIZATION", "3 windows without switching"],
    esp: ["ESP-NOW", "primary transport", "probe every 470 ms"],
    udp: ["UDP", "reserve through access point", "ESP-NOW probe every 940 ms"],
    down: ["loss ≥ 30%", "2 consecutive 5 s windows"],
    up: ["ACK ≥ 80%", "3 consecutive 5 s windows"],
    note: "Decisions use application ACKs. The 2/3-window hysteresis prevents oscillation near the threshold.",
  };
  const body = [
    text(80, 70, L.title, { size: 38, weight: 700 }),
    `<circle cx="155" cy="215" r="12" fill="${COLORS.ink}"/>`,
    text(155, 180, L.start, { size: 22, anchor: "middle", fill: COLORS.gray }),
    `<line x1="170" y1="215" x2="300" y2="215" stroke="${COLORS.gray}" stroke-width="4" marker-end="url(#arrow-gray)"/>`,
    `<rect x="315" y="140" width="420" height="150" fill="${COLORS.lighter}" stroke="${COLORS.ink}" stroke-width="3"/>`,
    text(525, 198, L.stabilize[0], { size: 29, weight: 700, anchor: "middle" }),
    text(525, 242, L.stabilize[1], { size: 23, anchor: "middle", fill: COLORS.gray }),
    `<line x1="735" y1="215" x2="880" y2="215" stroke="${COLORS.primary}" stroke-width="5" marker-end="url(#arrow-primary)"/>`,
    `<rect x="895" y="125" width="500" height="180" fill="#fff" stroke="${COLORS.primary}" stroke-width="5"/>`,
    text(1145, 185, L.esp[0], { size: 35, weight: 700, anchor: "middle", fill: COLORS.primary }),
    text(1145, 230, L.esp[1], { size: 25, anchor: "middle" }),
    text(1145, 270, L.esp[2], { size: 23, anchor: "middle", fill: COLORS.gray }),
    `<rect x="895" y="575" width="500" height="180" fill="#fff" stroke="${COLORS.reserve}" stroke-width="5"/>`,
    text(1145, 635, L.udp[0], { size: 35, weight: 700, anchor: "middle", fill: COLORS.reserve }),
    text(1145, 680, L.udp[1], { size: 25, anchor: "middle" }),
    text(1145, 720, L.udp[2], { size: 23, anchor: "middle", fill: COLORS.gray }),
    `<path d="M1395 215 C1515 215 1515 665 1395 665" fill="none" stroke="${COLORS.bad}" stroke-width="5" marker-end="url(#arrow-reserve)"/>`,
    multiline(1415, 430, L.down, { size: 20, lineHeight: 31, anchor: "middle", weight: 700, fill: COLORS.bad }),
    `<path d="M895 665 C775 665 775 215 895 215" fill="none" stroke="${COLORS.ok}" stroke-width="5" marker-end="url(#arrow-primary)"/>`,
    multiline(760, 410, L.up, { size: 23, lineHeight: 34, anchor: "middle", weight: 700, fill: COLORS.ok }),
    `<line x1="140" y1="850" x2="1460" y2="850" stroke="${COLORS.light}" stroke-width="2"/>`,
    text(800, 910, L.note, { size: 23, anchor: "middle" }),
  ].join("\n");
  return svg(1600, 980, body, L.title, L.note);
}

function timeline(lang) {
  const ru = lang === "ru";
  const L = ru ? {
    title: "Стандартизированный цикл управляемого отказа",
    prep: ["Подготовка", "≥ 30 с; ≥ 5 окон"],
    off: ["ACK OFF", "подавление ESP-NOW ACK"],
    fallback: ["Переход на UDP", "6,7–11,5 с"],
    on: ["ACK ON", "восстановление ответов"],
    recovery: ["Возврат к ESP-NOW", "13,8–18,4 с"],
    baseline: "ESP-NOW: 843/843 ACK до управляемого отказа",
    captured: "Журнал: команды, окна, sequence, CRC32, состояние транспорта и прикладные ACK",
  } : {
    title: "Standardized controlled-failure cycle",
    prep: ["Preparation", "≥ 30 s; ≥ 5 windows"],
    off: ["ACK OFF", "suppress ESP-NOW ACK"],
    fallback: ["Fallback to UDP", "6.7–11.5 s"],
    on: ["ACK ON", "restore acknowledgements"],
    recovery: ["Return to ESP-NOW", "13.8–18.4 s"],
    baseline: "ESP-NOW baseline: 843/843 application ACKs",
    captured: "Log: commands, windows, sequence, CRC32, transport state and application ACKs",
  };
  const xs = [130, 520, 790, 1080, 1360];
  const labels = [L.prep, L.off, L.fallback, L.on, L.recovery];
  const colors = [COLORS.gray, COLORS.bad, COLORS.reserve, COLORS.ok, COLORS.primary];
  let body = text(80, 70, L.title, { size: 38, weight: 700 });
  body += `<line x1="130" y1="380" x2="1470" y2="380" stroke="${COLORS.ink}" stroke-width="4" marker-end="url(#arrow-gray)"/>`;
  body += text(130, 270, L.baseline, { size: 24, weight: 700, fill: COLORS.primary });
  labels.forEach((label, i) => {
    const x = xs[i];
    body += `<line x1="${x}" y1="350" x2="${x}" y2="410" stroke="${colors[i]}" stroke-width="5"/>`;
    body += text(x, i % 2 === 0 ? 465 : 560, label[0], { size: 25, weight: 700, anchor: "middle", fill: colors[i] });
    body += text(x, i % 2 === 0 ? 505 : 600, label[1], { size: 21, anchor: "middle", fill: COLORS.gray });
    body += `<line x1="${x}" y1="415" x2="${x}" y2="${i % 2 === 0 ? 435 : 530}" stroke="${COLORS.light}" stroke-width="2"/>`;
  });
  body += `<rect x="150" y="700" width="1300" height="85" fill="${COLORS.lighter}" stroke="${COLORS.light}" stroke-width="2"/>`;
  body += text(800, 753, L.captured, { size: 22, anchor: "middle" });
  return svg(1600, 850, body, L.title, L.captured);
}

function results(lang) {
  const ru = lang === "ru";
  const L = ru ? {
    title: "Результаты 15 управляемых циклов",
    a: "а) Время перехода на UDP",
    b: "б) Время возврата к ESP-NOW",
    c: "в) Доставка прикладных ACK по UDP",
    ytime: "Время, с",
    ydelivery: "Доставка, %",
    note: "Точки — отдельные циклы; горизонтальная черта — среднее; у столбцов указаны число ACK и число probe.",
  } : {
    title: "Results of 15 controlled cycles",
    a: "a) Fallback time",
    b: "b) Recovery time",
    c: "c) UDP application-ACK delivery",
    ytime: "Time, s",
    ydelivery: "Delivery, %",
    note: "Dots are individual cycles; horizontal lines show means; bar labels report ACKs and probes.",
  };
  const pairs = ["8266–32", "8266–S3", "32–S3"];
  const fallback = [[6.738,8.295,8.077,8.657,6.678],[7.430,6.802,8.585,8.405,10.200],[6.995,9.799,10.849,11.500,10.191]];
  const recovery = [[14.304,14.165,14.472,18.278,14.851],[13.848,16.204,14.157,14.488,17.448],[16.245,18.359,13.949,18.392,16.445]];
  const means = [[7.689,8.284,9.867],[15.214,15.229,16.678]];
  const delivery = [90.226,96.992,68.519];
  const counts = ["120/133", "129/133", "74/108"];
  const panels = [{x:75,w:455,title:L.a,data:fallback,mean:means[0]},{x:575,w:455,title:L.b,data:recovery,mean:means[1]}];
  let body = text(65, 62, L.title, { size: 36, weight: 700 });
  const plotTop = 170, plotBottom = 650;
  const yMax = 20;
  for (const panel of panels) {
    const left = panel.x + 70, right = panel.x + panel.w - 20;
    body += text(panel.x + panel.w / 2, 125, panel.title, { size: 24, weight: 700, anchor: "middle" });
    body += `<line x1="${left}" y1="${plotTop}" x2="${left}" y2="${plotBottom}" stroke="${COLORS.ink}" stroke-width="2"/>`;
    body += `<line x1="${left}" y1="${plotBottom}" x2="${right}" y2="${plotBottom}" stroke="${COLORS.ink}" stroke-width="2"/>`;
    for (let tick=0; tick<=20; tick+=5) {
      const y = plotBottom - (tick / yMax) * (plotBottom - plotTop);
      body += `<line x1="${left}" y1="${y}" x2="${right}" y2="${y}" stroke="${tick===0 ? COLORS.ink : COLORS.light}" stroke-width="${tick===0 ? 2 : 1}"/>`;
      body += text(left - 12, y + 7, tick, { size: 18, anchor: "end", fill: COLORS.gray });
    }
    body += `<text x="${panel.x+18}" y="420" font-family="Arial" font-size="19" text-anchor="middle" fill="${COLORS.gray}" transform="rotate(-90 ${panel.x+18} 420)">${L.ytime}</text>`;
    panel.data.forEach((series, i) => {
      const x = left + 60 + i * 118;
      series.forEach((v, j) => {
        const dx = [-22,-11,0,11,22][j];
        const y = plotBottom - (v/yMax)*(plotBottom-plotTop);
        body += `<circle cx="${x+dx}" cy="${y}" r="5" fill="${COLORS.ink}"/>`;
      });
      const my = plotBottom - (panel.mean[i]/yMax)*(plotBottom-plotTop);
      body += `<line x1="${x-34}" y1="${my}" x2="${x+34}" y2="${my}" stroke="${COLORS.primary}" stroke-width="6"/>`;
      body += text(x, plotBottom + 32, pairs[i], { size: 17, anchor: "middle" });
      body += `<rect x="${x-42}" y="${my-32}" width="84" height="24" fill="#ffffff"/>`;
      body += text(x, my - 13, panel.mean[i].toFixed(3), { size: 17, weight: 700, anchor: "middle", fill: COLORS.primary });
    });
  }
  const px=1075,pw=465,left=1145,right=1515;
  body += text(px+pw/2,125,L.c,{size:24,weight:700,anchor:"middle"});
  body += `<line x1="${left}" y1="${plotTop}" x2="${left}" y2="${plotBottom}" stroke="${COLORS.ink}" stroke-width="2"/>`;
  body += `<line x1="${left}" y1="${plotBottom}" x2="${right}" y2="${plotBottom}" stroke="${COLORS.ink}" stroke-width="2"/>`;
  for(let tick=0;tick<=100;tick+=20){const y=plotBottom-(tick/100)*(plotBottom-plotTop);body+=`<line x1="${left}" y1="${y}" x2="${right}" y2="${y}" stroke="${tick===0?COLORS.ink:COLORS.light}" stroke-width="${tick===0?2:1}"/>`;body+=text(left-12,y+7,tick,{size:18,anchor:"end",fill:COLORS.gray});}
  body += `<text x="${px+18}" y="420" font-family="Arial" font-size="19" text-anchor="middle" fill="${COLORS.gray}" transform="rotate(-90 ${px+18} 420)">${L.ydelivery}</text>`;
  delivery.forEach((v,i)=>{const x=left+45+i*120;const y=plotBottom-(v/100)*(plotBottom-plotTop);body+=`<rect x="${x}" y="${y}" width="62" height="${plotBottom-y}" fill="#d9d9d9" stroke="${COLORS.ink}" stroke-width="2"/>`;body+=text(x+31,y-34,`${v.toFixed(3)} %`,{size:17,weight:700,anchor:"middle"});body+=text(x+31,y-12,counts[i],{size:16,anchor:"middle",fill:COLORS.gray});body+=text(x+31,plotBottom+32,pairs[i],{size:17,anchor:"middle"});});
  body += `<line x1="75" y1="720" x2="1525" y2="720" stroke="${COLORS.light}" stroke-width="2"/>`;
  body += text(800, 770, L.note, { size: 21, anchor: "middle" });
  return svg(1600, 820, body, L.title, L.note);
}

async function buildHardwareMontage() {
  const sources = [
    { file: process.env.WLF_ESP8266_PHOTO ?? path.join(ROOT, "article", "local_sources", "esp8266_esp12e.png"), label: "ESP8266 / ESP-12E" },
    { file: process.env.WLF_ESP32_PHOTO ?? path.join(ROOT, "article", "local_sources", "esp32_d0wd_v3.png"), label: "ESP32 / ESP32-D0WD-V3" },
    { file: process.env.WLF_ESP32S3_PHOTO ?? path.join(ROOT, "article", "local_sources", "esp32s3_n16r8.png"), label: "ESP32-S3 / N16R8" },
  ];

  const missing = sources.filter((source) => !fs.existsSync(source.file));
  if (missing.length > 0) {
    console.warn("Hardware montage was not rebuilt because local source photographs are missing:");
    for (const source of missing) console.warn(`  ${source.file}`);
    return;
  }

  const panels = [];
  for (const source of sources) {
    const photo = await sharp(source.file)
      .trim({ background: "#ffffff", threshold: 10 })
      .resize(445, 515, { fit: "contain", background: "#ffffff" })
      .png()
      .toBuffer();
    panels.push({ photo, label: source.label });
  }
  const composite = [];
  panels.forEach((panel, i) => {
    const left = 45 + i * 515;
    const frame = `<svg width="470" height="640" xmlns="http://www.w3.org/2000/svg"><rect x="1" y="1" width="468" height="638" rx="2" fill="#fff" stroke="#d9d9d9" stroke-width="2"/><line x1="1" y1="555" x2="469" y2="555" stroke="#d9d9d9" stroke-width="2"/><text x="235" y="606" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" font-size="25" font-weight="700" fill="#111">${esc(panel.label)}</text></svg>`;
    composite.push({ input: Buffer.from(frame), left, top: 25 });
    composite.push({ input: panel.photo, left: left + 13, top: 45 });
  });
  await sharp({ create: { width: 1590, height: 710, channels: 3, background: "#ffffff" } })
    .composite(composite)
    .png({ compressionLevel: 9 })
    .toFile(path.join(ARTICLE, "hardware_nodes.png"));
}

async function buildConsoleScreenshot() {
  const source = "C:/Users/warti/AppData/Local/Temp/codex-clipboard-d3c1a841-5aa9-4ad5-a5e9-3ce22943e581.png";
  const output = path.join(DOCS, "wireless_link_failover_console.png");
  await sharp(source)
    .extract({ left: 0, top: 0, width: 1920, height: 985 })
    .png({ compressionLevel: 9 })
    .toFile(output);
  await sharp(output).resize({ width: 1800 }).png({ compressionLevel: 9 }).toFile(path.join(ARTICLE, "console.png"));
}

const hardwareOnly = process.argv.includes("--hardware-only");
const schematicsOnly = process.argv.includes("--schematics-only");

if (!hardwareOnly) {
  for (const lang of ["ru", "en"]) {
    await writeSvgAndPng(`architecture_${lang}`, scientificArchitecture(lang), 2400);
    await writeSvgAndPng(`state_machine_${lang}`, scientificStateMachine(lang), 2400);
    if (schematicsOnly) continue;
    await writeSvgAndPng(`timeline_${lang}`, timeline(lang), 2200);
    await writeSvgAndPng(`results_${lang}`, results(lang), 2400);
  }
}
if (!schematicsOnly) await buildHardwareMontage();
if (!hardwareOnly && !schematicsOnly) await buildConsoleScreenshot();

for (const directory of [DOCS, ARTICLE]) {
  for (const file of fs.readdirSync(directory).sort()) {
    const full = path.join(directory, file);
    if (fs.statSync(full).isFile()) console.log(path.relative(ROOT, full), fs.statSync(full).size);
  }
}
