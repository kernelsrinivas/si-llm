export type Domain = "pcb" | "cad" | "cam" | "print" | "sim";

export type PcbPart = {
  ref: string;
  name: string;
  x: number;
  y: number;
  w: number;
  h: number;
};

export type DrcItem = {
  rule: string;
  status: "pass" | "warn";
  detail: string;
};

export type BomLine = { ref: string; mpn: string; qty: number; pkg: string };

export type StackLayer = { name: string; material: string; um: number };

export type PcbModel = {
  title: string;
  brief: string;
  widthMm: number;
  heightMm: number;
  layers: number;
  stage: number;
  parts: PcbPart[];
  nets: { name: string; refs: string[] }[];
  bom: BomLine[];
  stackup: StackLayer[];
  drc: DrcItem[];
  gerbers: string[];
  notes: string[];
};

export type CadMaterial = "6061-T6" | "ABS" | "PETG" | "316L";

export type CadModel = {
  name: string;
  length: number;
  width: number;
  thickness: number;
  hole: number;
  fillet: number;
  material: CadMaterial;
};

export type CamStock = "aluminum" | "abs" | "delrin";

export type CamModel = {
  toolMm: number;
  feed: number;
  spindle: number;
  stepdown: number;
  stock: CamStock;
};

export type PrintMaterial = "PLA" | "PETG" | "ABS" | "Resin";

export type PrintModel = {
  material: PrintMaterial;
  nozzle: number;
  layer: number;
  infill: number;
  walls: number;
  supports: boolean;
  bed: number;
};

export type SimKind = "thermal" | "stress" | "signal";

export type SimPoint = { step: string; value: number; limit: number };

export type Adapter = {
  clearanceMm: number;
  traceMm: number;
  safety: number;
  printMaterial: PrintMaterial;
  camFeedScale: number;
  lessons: number;
};

export type Lesson = {
  id: string;
  domain: Domain;
  title: string;
  note: string;
  apply: Partial<Adapter>;
};

export type Turn = {
  id: string;
  role: "you" | "si";
  text: string;
  domain: Domain | "studio";
  modality: "text" | "voice" | "vision";
  at: number;
  stars?: number;
};

export type VisionRead = {
  name: string;
  label: Domain | "unknown";
  edge: number;
  luma: number;
  copper: number;
  note: string;
};

export const PCB_STAGES = [
  "Requirements",
  "Schematic",
  "Netlist",
  "Placement",
  "Routing",
  "DRC",
  "Stackup",
  "Release",
] as const;

export const SEED_ADAPTER: Adapter = {
  clearanceMm: 0.16,
  traceMm: 0.25,
  safety: 1.4,
  printMaterial: "PLA",
  camFeedScale: 1,
  lessons: 0,
};

export const LIBRARY: Lesson[] = [
  {
    id: "clr",
    domain: "pcb",
    title: "Open clearance on 2-layer",
    note: "Fab house prefers 0.2 mm copper-to-copper on prototype panels.",
    apply: { clearanceMm: 0.2 },
  },
  {
    id: "tr",
    domain: "pcb",
    title: "USB VBUS current",
    note: "1 oz copper, 1.5 A continuous, wants about 0.6 mm trace.",
    apply: { traceMm: 0.6 },
  },
  {
    id: "sf",
    domain: "sim",
    title: "Bracket safety factor",
    note: "Mechanical release gate is 2.0 against yield, not 1.4.",
    apply: { safety: 2 },
  },
  {
    id: "petg",
    domain: "print",
    title: "Functional PETG",
    note: "Brackets that see heat or outdoor use print in PETG, not PLA.",
    apply: { printMaterial: "PETG" },
  },
  {
    id: "feed",
    domain: "cam",
    title: "Aluminum finish pass",
    note: "Drop feed 15% on 6061 to keep chatter out of the pocket floor.",
    apply: { camFeedScale: 0.85 },
  },
];

const DENS: Record<CadMaterial, number> = {
  "6061-T6": 2.7,
  ABS: 1.05,
  PETG: 1.27,
  "316L": 8.0,
};

export function cadVolumeCm3(cad: CadModel): number {
  const plate = (cad.length * cad.width * cad.thickness) / 1000;
  const hole =
    cad.hole > 0
      ? (Math.PI * (cad.hole / 2) ** 2 * cad.thickness) / 1000
      : 0;
  return Math.max(0.05, plate - hole);
}

export function cadMassG(cad: CadModel): number {
  return cadVolumeCm3(cad) * DENS[cad.material];
}

function stackup(layers: number): StackLayer[] {
  if (layers >= 4) {
    return [
      { name: "L1 Signal", material: "Cu 1 oz", um: 35 },
      { name: "Prepreg", material: "2116", um: 100 },
      { name: "L2 Ground", material: "Cu 1 oz", um: 35 },
      { name: "Core", material: "FR-4", um: 800 },
      { name: "L3 Power", material: "Cu 1 oz", um: 35 },
      { name: "Prepreg", material: "2116", um: 100 },
      { name: "L4 Signal", material: "Cu 1 oz", um: 35 },
    ];
  }
  return [
    { name: "Top copper", material: "Cu 1 oz", um: 35 },
    { name: "Core", material: "FR-4", um: 1600 },
    { name: "Bottom copper", material: "Cu 1 oz", um: 35 },
  ];
}

type Template = Omit<PcbModel, "stage" | "drc" | "stackup" | "gerbers" | "notes">;

const TEMPLATES: { keys: string[]; board: Template }[] = [
  {
    keys: ["motor", "drv", "bldc", "driver"],
    board: {
      title: "4-layer motor driver",
      brief: "24 V three-phase gate drive with shunt sensing",
      widthMm: 60,
      heightMm: 40,
      layers: 4,
      parts: [
        { ref: "U1", name: "DRV8316", x: 38, y: 36, w: 22, h: 22 },
        { ref: "U2", name: "Buck 5V", x: 12, y: 18, w: 14, h: 12 },
        { ref: "J1", name: "XT30", x: 8, y: 70, w: 16, h: 12 },
        { ref: "J2", name: "Motor", x: 78, y: 62, w: 16, h: 18 },
        { ref: "R1", name: "Shunt", x: 58, y: 72, w: 12, h: 8 },
        { ref: "C1", name: "Bulk", x: 22, y: 48, w: 10, h: 12 },
      ],
      nets: [
        { name: "VM", refs: ["J1", "U2", "C1", "U1"] },
        { name: "PHA", refs: ["U1", "J2"] },
        { name: "ISEN", refs: ["R1", "U1"] },
        { name: "GND", refs: ["J1", "U1", "U2", "R1"] },
      ],
      bom: [
        { ref: "U1", mpn: "DRV8316R", qty: 1, pkg: "QFN-40" },
        { ref: "U2", mpn: "TPS54302", qty: 1, pkg: "SOT-23-6" },
        { ref: "R1", mpn: "WSL2512 2mΩ", qty: 1, pkg: "2512" },
        { ref: "C1", mpn: "100µF 35V", qty: 1, pkg: "ELEC" },
        { ref: "J1", mpn: "XT30PW", qty: 1, pkg: "TH" },
        { ref: "J2", mpn: "PH-3P", qty: 1, pkg: "TH" },
      ],
    },
  },
  {
    keys: ["rf", "nrf", "ble", "antenna", "beacon"],
    board: {
      title: "BLE beacon",
      brief: "nRF52840 module, chip antenna, coin cell",
      widthMm: 28,
      heightMm: 36,
      layers: 2,
      parts: [
        { ref: "U1", name: "nRF52840", x: 42, y: 32, w: 26, h: 20 },
        { ref: "AE1", name: "Chip ant", x: 78, y: 18, w: 14, h: 8 },
        { ref: "BT1", name: "CR2032", x: 30, y: 72, w: 28, h: 18 },
        { ref: "C1", name: "Match", x: 64, y: 28, w: 8, h: 6 },
        { ref: "L1", name: "Match", x: 64, y: 40, w: 8, h: 6 },
        { ref: "SW1", name: "Tact", x: 12, y: 22, w: 10, h: 10 },
      ],
      nets: [
        { name: "RF", refs: ["U1", "C1", "L1", "AE1"] },
        { name: "VDD", refs: ["BT1", "U1"] },
        { name: "GND", refs: ["BT1", "U1", "AE1"] },
      ],
      bom: [
        { ref: "U1", mpn: "nRF52840-QIAA", qty: 1, pkg: "aQFN" },
        { ref: "AE1", mpn: "2450AT18A100", qty: 1, pkg: "SMD" },
        { ref: "BT1", mpn: "CR2032 holder", qty: 1, pkg: "TH" },
        { ref: "C1", mpn: "1.5 pF C0G", qty: 1, pkg: "0402" },
        { ref: "L1", mpn: "3.3 nH", qty: 1, pkg: "0402" },
        { ref: "SW1", mpn: "PTS810", qty: 1, pkg: "SMD" },
      ],
    },
  },
  {
    keys: ["psu", "bench", "supply", "buck"],
    board: {
      title: "Bench front-end",
      brief: "Buck preregulator, sense, and OLED status",
      widthMm: 80,
      heightMm: 50,
      layers: 2,
      parts: [
        { ref: "U1", name: "Buck", x: 28, y: 30, w: 18, h: 14 },
        { ref: "U2", name: "Sense", x: 55, y: 34, w: 14, h: 12 },
        { ref: "L1", name: "Inductor", x: 28, y: 54, w: 16, h: 14 },
        { ref: "J1", name: "Barrel", x: 8, y: 22, w: 12, h: 14 },
        { ref: "J2", name: "Banana", x: 86, y: 40, w: 10, h: 22 },
        { ref: "OLED", name: "0.96\"", x: 62, y: 68, w: 24, h: 16 },
      ],
      nets: [
        { name: "VIN", refs: ["J1", "U1"] },
        { name: "SW", refs: ["U1", "L1"] },
        { name: "VOUT", refs: ["L1", "U2", "J2", "OLED"] },
        { name: "GND", refs: ["J1", "U1", "J2"] },
      ],
      bom: [
        { ref: "U1", mpn: "TPS54560", qty: 1, pkg: "SO-8" },
        { ref: "U2", mpn: "INA226", qty: 1, pkg: "VSSOP" },
        { ref: "L1", mpn: "10µH 5A", qty: 1, pkg: "SMD" },
        { ref: "J1", mpn: "PJ-002A", qty: 1, pkg: "TH" },
        { ref: "J2", mpn: "Binding post", qty: 1, pkg: "TH" },
        { ref: "OLED", mpn: "SSD1306", qty: 1, pkg: "HDR" },
      ],
    },
  },
  {
    keys: ["usb", "esp", "sensor", "imu", "node"],
    board: {
      title: "USB-C sensor node",
      brief: "ESP32-S3, USB-C, 3.3 V LDO, IMU and temperature",
      widthMm: 42,
      heightMm: 28,
      layers: 2,
      parts: [
        { ref: "U1", name: "ESP32-S3", x: 46, y: 42, w: 28, h: 22 },
        { ref: "J1", name: "USB-C", x: 12, y: 18, w: 16, h: 12 },
        { ref: "U2", name: "LDO 3V3", x: 22, y: 48, w: 12, h: 10 },
        { ref: "U3", name: "IMU", x: 74, y: 28, w: 14, h: 12 },
        { ref: "U4", name: "Temp", x: 74, y: 58, w: 12, h: 10 },
        { ref: "C1", name: "Decap", x: 34, y: 24, w: 8, h: 6 },
      ],
      nets: [
        { name: "VBUS", refs: ["J1", "U2"] },
        { name: "3V3", refs: ["U2", "U1", "U3", "U4", "C1"] },
        { name: "USB", refs: ["J1", "U1"] },
        { name: "I2C", refs: ["U1", "U3", "U4"] },
        { name: "GND", refs: ["J1", "U1", "U2", "U3"] },
      ],
      bom: [
        { ref: "U1", mpn: "ESP32-S3-WROOM-1", qty: 1, pkg: "Module" },
        { ref: "J1", mpn: "TYPE-C-31-M-12", qty: 1, pkg: "SMD" },
        { ref: "U2", mpn: "AP2112K-3.3", qty: 1, pkg: "SOT-23-5" },
        { ref: "U3", mpn: "ICM-42688-P", qty: 1, pkg: "LGA-14" },
        { ref: "U4", mpn: "TMP117", qty: 1, pkg: "WSON" },
        { ref: "C1", mpn: "10µF 10V", qty: 1, pkg: "0603" },
      ],
    },
  },
];

export function pickTemplate(brief: string): Template {
  const q = brief.toLowerCase();
  const hit = TEMPLATES.find((t) => t.keys.some((k) => q.includes(k)));
  return hit?.board ?? TEMPLATES[TEMPLATES.length - 1]!.board;
}

export function buildPcb(brief: string, adapter: Adapter, prior?: PcbModel): PcbModel {
  const base = brief.trim() ? pickTemplate(brief) : pickTemplate(prior?.brief || "sensor");
  const layers = base.layers;
  const currentNeed = base.nets.some((n) => n.name === "VM" || n.name === "VBUS") ? 0.55 : 0.2;
  const drc: DrcItem[] = [
    {
      rule: "Clearance",
      status: adapter.clearanceMm >= 0.15 ? "pass" : "warn",
      detail: `Copper clearance ${adapter.clearanceMm.toFixed(2)} mm vs 0.15 mm fab minimum.`,
    },
    {
      rule: "Trace width",
      status: adapter.traceMm + 0.001 >= currentNeed ? "pass" : "warn",
      detail: `Power nets use ${adapter.traceMm.toFixed(2)} mm. This board wants ≥ ${currentNeed.toFixed(2)} mm on 1 oz.`,
    },
    {
      rule: "Annular ring",
      status: "pass",
      detail: "0.15 mm ring on all vias, drill 0.3 mm.",
    },
    {
      rule: layers >= 4 ? "Return path" : "USB pair",
      status: layers >= 4 || !base.nets.some((n) => n.name === "USB") ? "pass" : "warn",
      detail:
        layers >= 4
          ? "Ground plane on L2 is unbroken under the gate driver."
          : base.nets.some((n) => n.name === "USB")
            ? "USB D+/D− length-matched within 0.1 mm, but a 2-layer pour is the return. Keep the pair over the pour."
            : "RF keep-out under the antenna is clear of copper.",
    },
    {
      rule: "Courtyard",
      status: "pass",
      detail: `${base.parts.length} parts placed with 0.4 mm courtyard gap.`,
    },
  ];
  const warns = drc.filter((d) => d.status === "warn").length;
  return {
    ...base,
    brief: brief.trim() || base.brief,
    stage: 7,
    stackup: stackup(layers),
    gerbers: [
      "F.Cu",
      "B.Cu",
      ...(layers >= 4 ? ["In1.Cu", "In2.Cu"] : []),
      "F.Mask",
      "B.Mask",
      "F.Silk",
      "Edge.Cuts",
      "Drill.npth",
      "Drill.pth",
    ],
    drc,
    notes: [
      `${base.widthMm} × ${base.heightMm} mm, ${layers}-layer, ${adapter.traceMm.toFixed(2)} mm default trace, ${adapter.clearanceMm.toFixed(2)} mm clearance.`,
      warns
        ? `${warns} DRC warning${warns > 1 ? "s" : ""} — release is held until they are waived or fixed.`
        : "DRC clean. Gerbers and BOM are ready to pack.",
    ],
  };
}

export function camProgram(cad: CadModel, cam: CamModel, adapter: Adapter): string {
  const feed = Math.round(cam.feed * adapter.camFeedScale);
  const z = (-cad.thickness).toFixed(2);
  const pocket = (cad.hole / 2).toFixed(2);
  return [
    "(SI-LLM CAM — contour + hole)",
    "G21 G90 G17 G54",
    `S${cam.spindle} M3`,
    "G0 Z5.000",
    "G0 X0 Y0",
    `G1 Z${(-cam.stepdown).toFixed(3)} F${Math.round(feed * 0.4)}`,
    `G1 X${cad.length.toFixed(3)} Y0 F${feed}`,
    `G1 X${cad.length.toFixed(3)} Y${cad.width.toFixed(3)}`,
    `G1 X0 Y${cad.width.toFixed(3)}`,
    "G1 X0 Y0",
    `G0 Z5.000`,
    `G0 X${(cad.length / 2).toFixed(3)} Y${(cad.width / 2).toFixed(3)}`,
    `G1 Z${z} F${Math.round(feed * 0.35)}`,
    `G2 I${pocket} F${Math.round(feed * 0.7)}`,
    "G0 Z5.000",
    "M5",
    "M30",
  ].join("\n");
}

export function printPlan(print: PrintModel, cad: CadModel) {
  const vol = cadVolumeCm3({ ...cad, material: "PETG" });
  const solid = print.material === "Resin" ? 1 : 0.15 + (print.infill / 100) * 0.85;
  const used = vol * (print.material === "Resin" ? 1.05 : solid * (1 + print.walls * 0.04));
  const density = print.material === "Resin" ? 1.1 : print.material === "ABS" ? 1.04 : print.material === "PETG" ? 1.27 : 1.24;
  const grams = used * density;
  const flow = print.material === "Resin" ? 0 : 8 * (print.nozzle / 0.4);
  const minutes =
    print.material === "Resin"
      ? Math.round((cad.thickness / 0.05) * 8 + 40)
      : Math.round((used / Math.max(0.4, flow)) * 60 + (cad.thickness / print.layer) * 0.4);
  const layers = print.material === "Resin" ? Math.round(cad.thickness / 0.05) : Math.max(1, Math.round(cad.thickness / print.layer));
  return { grams, minutes, layers, used };
}

const YIELD: Record<CadMaterial, number> = {
  "6061-T6": 276,
  ABS: 40,
  PETG: 50,
  "316L": 290,
};

export function simSeries(kind: SimKind, cad: CadModel, adapter: Adapter): SimPoint[] {
  if (kind === "thermal") {
    const sink = cad.material === "6061-T6" || cad.material === "316L" ? 18 : 42;
    return [0, 1, 2, 5, 10, 20, 40].map((t, i) => {
      const rise = sink * (1 - Math.exp(-t / 8));
      return {
        step: t === 0 ? "0s" : `${t}s`,
        value: Math.round((25 + rise) * 10) / 10,
        limit: 85 - i * 0,
      };
    });
  }
  if (kind === "stress") {
    const yieldMpa = YIELD[cad.material];
    const allow = yieldMpa / adapter.safety;
    return [10, 25, 40, 55, 70, 85, 100].map((load) => {
      const stress = (load / 40) * (8 / Math.max(1.2, cad.thickness)) * (40 / cad.width) * 18;
      return {
        step: `${load}N`,
        value: Math.round(stress * 10) / 10,
        limit: Math.round(allow),
      };
    });
  }
  return [0.1, 0.5, 1, 2, 3, 4, 5].map((ghz) => ({
    step: `${ghz}G`,
    value: Math.round((-0.4 - ghz * 1.15 - (adapter.traceMm < 0.2 ? 0.8 : 0)) * 10) / 10,
    limit: -8,
  }));
}

export function detectDomain(text: string): Domain | "studio" {
  const q = text.toLowerCase();
  if (/\b(pcb|schematic|gerber|netlist|bom|drc|stackup|board)\b/.test(q)) return "pcb";
  if (/\b(g-?code|toolpath|cnc|cam|endmill|spindle|pocket)\b/.test(q)) return "cam";
  if (/\b(print|slic|infill|nozzle|pla|petg|filament|resin)\b/.test(q)) return "print";
  if (/\b(stress|thermal|fea|simul|signal|eye diagram|yield)\b/.test(q)) return "sim";
  if (/\b(cad|bracket|extrude|fillet|step|solid|hole)\b/.test(q)) return "cad";
  return "studio";
}

export function answer(input: {
  text: string;
  domainHint: Domain | "studio";
  modality: Turn["modality"];
  adapter: Adapter;
  pcb: PcbModel;
  cad: CadModel;
  cam: CamModel;
  print: PrintModel;
  simKind: SimKind;
  vision?: VisionRead | null;
}): { text: string; domain: Domain | "studio"; pcb?: PcbModel; print?: PrintModel } {
  const hinted = input.domainHint === "studio" ? detectDomain(input.text) : input.domainHint;
  const domain = hinted;
  const bits: string[] = [];

  if (input.modality === "voice") bits.push("Heard you.");
  if (input.modality === "vision" && input.vision) {
    bits.push(
      `Vision pass on ${input.vision.name}: ${input.vision.label} read, edge density ${(input.vision.edge * 100).toFixed(0)}%, luma ${input.vision.luma.toFixed(0)}. ${input.vision.note}`,
    );
  }

  if (domain === "pcb" || (domain === "studio" && /\b(design|make|build)\b/i.test(input.text))) {
    const pcb = buildPcb(input.text, input.adapter, input.pcb);
    const warn = pcb.drc.filter((d) => d.status === "warn");
    bits.push(
      `${pcb.title}. ${pcb.widthMm}×${pcb.heightMm} mm, ${pcb.layers} layers. Flow ran requirements → release.`,
      `Netlist: ${pcb.nets.map((n) => n.name).join(", ")}.`,
      `BOM ${pcb.bom.length} lines. Gerbers: ${pcb.gerbers.join(", ")}.`,
      warn.length
        ? `DRC holds release: ${warn.map((w) => w.rule).join(", ")}. ${warn[0]!.detail}`
        : "DRC is clean against the current adapter.",
      `Adapter trace ${input.adapter.traceMm.toFixed(2)} mm, clearance ${input.adapter.clearanceMm.toFixed(2)} mm (${input.adapter.lessons} lessons applied).`,
    );
    return { text: bits.join(" "), domain: "pcb", pcb };
  }

  if (domain === "cad") {
    const mass = cadMassG(input.cad);
    bits.push(
      `${input.cad.name}: ${input.cad.length}×${input.cad.width}×${input.cad.thickness} mm ${input.cad.material}, Ø${input.cad.hole} hole, R${input.cad.fillet} fillet.`,
      `Volume ${cadVolumeCm3(input.cad).toFixed(2)} cm³, mass ${mass.toFixed(1)} g.`,
      "Feature tree: sketch rectangle → extrude → hole → fillet. STEP export is the feature script in the CAD desk.",
    );
    return { text: bits.join(" "), domain: "cad" };
  }

  if (domain === "cam") {
    const feed = Math.round(input.cam.feed * input.adapter.camFeedScale);
    bits.push(
      `CAM for the ${input.cad.name} in ${input.cam.stock}. Ø${input.cam.toolMm} mm end mill, ${feed} mm/min (${input.adapter.camFeedScale === 1 ? "nominal" : "lesson-scaled"}), ${input.cam.spindle} rpm, ${input.cam.stepdown} mm stepdown.`,
      "Ops: face not required (plate stock), contour of the outline, then helical bore of the center hole. G-code is on the CAM desk — M30 closes the program.",
    );
    return { text: bits.join(" "), domain: "cam" };
  }

  if (domain === "print") {
    const plan = printPlan(input.print, input.cad);
    bits.push(
      `${input.print.material} on a ${input.print.bed} mm bed. ${plan.layers} layers, ${input.print.infill}% infill, ${input.print.walls} walls${input.print.supports ? ", supports on" : ", no supports"}.`,
      `Estimate ${plan.grams.toFixed(1)} g and ${plan.minutes} min for the current solid.`,
      input.adapter.printMaterial !== input.print.material
        ? `Training adapter prefers ${input.adapter.printMaterial}. Switch material if this is a functional part.`
        : "Material matches the trained preference.",
    );
    return { text: bits.join(" "), domain: "print" };
  }

  if (domain === "sim") {
    const series = simSeries(input.simKind, input.cad, input.adapter);
    const last = series[series.length - 1]!;
    const over = series.some((p) =>
      input.simKind === "signal" ? p.value < p.limit : p.value > p.limit,
    );
    const label =
      input.simKind === "thermal"
        ? "junction temperature"
        : input.simKind === "stress"
          ? "von Mises"
          : "insertion loss";
    bits.push(
      `${label} across ${series.length} steps. Last point ${last.value} against limit ${last.limit}. Safety factor in the adapter is ${input.adapter.safety.toFixed(1)}.`,
      over
        ? "At least one sample crosses the limit. Do not release until thickness, copper, or material changes."
        : "All samples stay inside the limit for this load case.",
    );
    return { text: bits.join(" "), domain: "sim" };
  }

  bits.push(
    "SI-LLM covers the whole hardware loop: PCB (schematic through Gerber), CAD solids, CAM toolpaths, 3D print plans, and thermal / stress / signal simulation.",
    "Ask in text, hold the mic, or drop a photo. Training lessons on the Train desk change clearance, trace width, feeds, print material, and the simulation safety factor.",
    `Live board is “${input.pcb.title}”. Solid is “${input.cad.name}”.`,
  );
  return { text: bits.join(" "), domain: "studio" };
}

export function readVision(
  name: string,
  pixels: Uint8ClampedArray,
  forced?: Domain,
): VisionRead {
  let luma = 0;
  let copper = 0;
  let edge = 0;
  const n = Math.max(1, pixels.length / 4);
  let prev = 0;
  for (let i = 0; i < pixels.length; i += 4) {
    const r = pixels[i] ?? 0;
    const g = pixels[i + 1] ?? 0;
    const b = pixels[i + 2] ?? 0;
    const y = 0.2126 * r + 0.7152 * g + 0.0722 * b;
    luma += y;
    if (r > g + 18 && r > b + 10 && r > 70) copper += 1;
    edge += Math.abs(y - prev);
    prev = y;
  }
  luma /= n;
  const copperRatio = copper / n;
  const edgeNorm = Math.min(1, edge / n / 40);
  let label: VisionRead["label"] = "unknown";
  let note = "No strong hardware signature. Label it so the next lesson sticks.";
  if (copperRatio > 0.08) {
    label = "pcb";
    note = "Copper-colored regions dominate. Treat as a fabricated board: look for soldermask openings, connectors, and pour continuity.";
  } else if (edgeNorm > 0.55 && luma > 140) {
    label = "cad";
    note = "High-contrast edges on a bright field. Reads as a CAD render or a machined part on a light bench.";
  } else if (luma < 70 && edgeNorm > 0.25) {
    label = "print";
    note = "Dark layered texture. Reads as a printed part or a failed layer photo — check first-layer squish and stringing.";
  } else if (edgeNorm > 0.35) {
    label = "cam";
    note = "Busy edge field without copper tint. Reads as a toolpath plot or a chip photo.";
  }
  if (forced) {
    label = forced;
    note = `You labeled this ${forced}. That correction is a training example.`;
  }
  return { name, label, edge: edgeNorm, luma, copper: copperRatio, note };
}

export function applyLesson(adapter: Adapter, lesson: Lesson): Adapter {
  return {
    ...adapter,
    ...lesson.apply,
    lessons: adapter.lessons + 1,
  };
}

export function lessonFromNote(note: string): Lesson {
  const q = note.toLowerCase();
  const apply: Partial<Adapter> = {};
  if (/clearance/.test(q)) apply.clearanceMm = 0.2;
  if (/trace|vbus|amp/.test(q)) apply.traceMm = 0.6;
  if (/safety|yield/.test(q)) apply.safety = 2;
  if (/petg/.test(q)) apply.printMaterial = "PETG";
  if (/\babs\b/.test(q)) apply.printMaterial = "ABS";
  if (/\bpla\b/.test(q)) apply.printMaterial = "PLA";
  if (/resin/.test(q)) apply.printMaterial = "Resin";
  if (/feed|chatter/.test(q)) apply.camFeedScale = 0.85;
  const domain = detectDomain(note);
  return {
    id: `note-${Math.random().toString(36).slice(2, 8)}`,
    domain: domain === "studio" ? "pcb" : domain,
    title: note.slice(0, 52),
    note,
    apply,
  };
}

export function scoreboard(turns: Turn[]) {
  const rated = turns.filter((t) => t.role === "si" && typeof t.stars === "number");
  const by = (d: Domain) => {
    const rows = rated.filter((t) => t.domain === d);
    const avg = rows.length ? rows.reduce((s, t) => s + (t.stars ?? 0), 0) / rows.length : 0;
    return { n: rows.length, avg };
  };
  return {
    pcb: by("pcb"),
    cad: by("cad"),
    cam: by("cam"),
    print: by("print"),
    sim: by("sim"),
    total: rated.length,
  };
}
