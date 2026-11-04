import { useEffect, useState, type ReactNode } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  LIBRARY,
  PCB_STAGES,
  cadMassG,
  cadVolumeCm3,
  camProgram,
  printPlan,
  scoreboard,
  simSeries,
  type CadModel,
  type Domain,
  type PcbModel,
} from "@/lib/si/model";
import { useSi } from "@/lib/si/store";

const tipStyle = {
  background: "#161c20",
  border: "1px solid #2c3840",
  borderRadius: 8,
  color: "#e7eef2",
  fontSize: 12,
};

function Panel({
  title,
  kicker,
  children,
  action,
}: {
  title: string;
  kicker: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <section className="flex flex-col gap-3 rounded-lg border border-line bg-surface p-4">
      <header className="flex items-start justify-between gap-3">
        <div>
          <p className="font-mono text-xs tracking-wide text-copper uppercase">{kicker}</p>
          <h2 className="text-lg font-semibold tracking-tight">{title}</h2>
        </div>
        {action}
      </header>
      {children}
    </section>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <label className="flex min-w-0 flex-1 flex-col gap-1 text-xs text-muted">
      {label}
      {children}
    </label>
  );
}

const inputCls =
  "h-11 rounded-md border border-line bg-bg px-3 text-sm text-fg outline-none focus:border-copper";

export function BriefView() {
  const loadBrief = useSi((s) => s.loadBrief);
  const adapter = useSi((s) => s.adapter);
  const presets = [
    { id: "usb", label: "USB-C sensor node", brief: "usb-c esp32 sensor imu" },
    { id: "motor", label: "Motor driver", brief: "bldc motor driver 24v" },
    { id: "rf", label: "BLE beacon", brief: "nrf ble beacon antenna" },
    { id: "psu", label: "Bench front-end", brief: "bench psu buck sense" },
  ];
  return (
    <div className="grid gap-4 lg:grid-cols-5">
      <Panel
        kicker="SI-LLM"
        title="Hardware specialist"
        action={
          <span className="rounded-md border border-line px-2 py-1 font-mono text-xs text-muted">
            {adapter.lessons} lessons
          </span>
        }
      >
        <p className="text-sm text-muted">
          One model desk for the loop from a blank requirement to a releasable board, a solid, a
          toolpath, a print, and a simulation. The local adapter is what Train edits. Ask below, or
          start from a known brief.
        </p>
        <div className="grid gap-2 sm:grid-cols-2">
          {presets.map((p) => (
            <button
              key={p.id}
              type="button"
              onClick={() => loadBrief(p.brief)}
              className="h-11 rounded-md border border-line bg-raised px-3 text-left text-sm hover:border-copper"
            >
              {p.label}
            </button>
          ))}
        </div>
      </Panel>
      <div className="grid gap-3 sm:grid-cols-2 lg:col-span-2 lg:grid-cols-1">
        {[
          ["PCB", "Requirements through Gerber, BOM, and DRC"],
          ["CAD", "Parametric plate, mass, feature tree"],
          ["CAM", "Feeds, speeds, and a closed G-code program"],
          ["Print", "Material, infill, time, and filament"],
          ["Sim", "Thermal, stress, and insertion loss"],
        ].map(([name, line]) => (
          <div key={name} className="rounded-lg border border-line bg-raised px-3 py-3">
            <p className="text-sm font-medium">{name}</p>
            <p className="text-xs text-muted">{line}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

export function PcbView() {
  const pcb = useSi((s) => s.pcb);
  const setPcbStage = useSi((s) => s.setPcbStage);
  const loadBrief = useSi((s) => s.loadBrief);
  const [playing, setPlaying] = useState(false);

  useEffect(() => {
    if (!playing || pcb.stage >= 7) return;
    const t = window.setTimeout(() => setPcbStage(pcb.stage + 1), 280);
    return () => window.clearTimeout(t);
  }, [playing, pcb.stage, setPcbStage]);

  useEffect(() => {
    if (pcb.stage >= 7) setPlaying(false);
  }, [pcb.stage]);

  return (
    <div className="grid gap-4 xl:grid-cols-5">
      <div className="flex flex-col gap-4 xl:col-span-3">
        <Panel
          kicker="PCB flow"
          title={pcb.title}
          action={
            <button
              type="button"
              className="h-11 rounded-md bg-copper px-4 text-sm font-medium text-copper-ink"
              onClick={() => {
                loadBrief(pcb.brief);
                setPlaying(true);
              }}
            >
              Run flow
            </button>
          }
        >
          <p className="text-sm text-muted">
            {pcb.widthMm} × {pcb.heightMm} mm · {pcb.layers} layers · {pcb.brief}
          </p>
          <div className="flex gap-1 overflow-x-auto pb-1">
            {PCB_STAGES.map((name, i) => {
              const on = i <= pcb.stage;
              return (
                <button
                  key={name}
                  type="button"
                  onClick={() => {
                    setPlaying(false);
                    setPcbStage(i);
                  }}
                  className={
                    "h-11 shrink-0 rounded-md border px-3 text-xs " +
                    (on
                      ? "border-copper bg-copper text-copper-ink"
                      : "border-line bg-bg text-muted")
                  }
                >
                  {i + 1} {name}
                </button>
              );
            })}
          </div>
          <Board pcb={pcb} />
          <ul className="flex flex-col gap-1 text-sm text-muted">
            {pcb.notes.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        </Panel>
      </div>
      <div className="flex flex-col gap-4 xl:col-span-2">
        <Panel kicker="DRC" title={pcb.stage >= 5 ? "Rule check" : "Locked until route"}>
          {pcb.stage < 5 ? (
            <p className="text-sm text-muted">Routing has to finish before copper rules run.</p>
          ) : (
            <ul className="flex flex-col gap-2">
              {pcb.drc.map((d) => (
                <li key={d.rule} className="rounded-md border border-line bg-bg px-3 py-2">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-medium">{d.rule}</span>
                    <span className="font-mono text-xs text-copper uppercase">{d.status}</span>
                  </div>
                  <p className="text-xs text-muted">{d.detail}</p>
                </li>
              ))}
            </ul>
          )}
        </Panel>
        <Panel kicker="Release pack" title={pcb.stage >= 7 ? "BOM, stackup, Gerber" : "Still in flow"}>
          {pcb.stage < 7 ? (
            <p className="text-sm text-muted">Release files appear after stackup.</p>
          ) : (
            <>
              <div className="flex flex-wrap gap-1">
                {pcb.gerbers.map((g) => (
                  <span key={g} className="rounded-md border border-line px-2 py-1 font-mono text-xs text-muted">
                    {g}
                  </span>
                ))}
              </div>
              <table className="w-full text-left text-xs">
                <thead className="text-faint">
                  <tr>
                    <th className="py-1 font-medium">Ref</th>
                    <th className="font-medium">MPN</th>
                    <th className="font-medium">Pkg</th>
                  </tr>
                </thead>
                <tbody>
                  {pcb.bom.map((b) => (
                    <tr key={b.ref} className="border-t border-line">
                      <td className="py-1 font-mono">{b.ref}</td>
                      <td>{b.mpn}</td>
                      <td className="text-muted">{b.pkg}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <ul className="text-xs text-muted">
                {pcb.stackup.map((l) => (
                  <li key={l.name} className="flex justify-between gap-2 border-t border-line py-1">
                    <span>{l.name}</span>
                    <span className="font-mono">
                      {l.material} · {l.um} µm
                    </span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </Panel>
      </div>
    </div>
  );
}

function Board({ pcb }: { pcb: PcbModel }) {
  const showParts = pcb.stage >= 3;
  const showRoute = pcb.stage >= 4;
  return (
    <div className="aspect-[5/3] w-full rounded-md border border-line bg-bg">
      <svg viewBox="0 0 100 78" className="h-full w-full">
        <rect x="3" y="3" width="94" height="72" rx="2" fill="#14110e" stroke="#e08a45" strokeWidth="0.5" />
        {showRoute &&
          pcb.nets.map((net) => {
            const pts = net.refs
              .map((ref) => pcb.parts.find((p) => p.ref === ref))
              .filter((p): p is PcbModel["parts"][number] => Boolean(p));
            if (pts.length < 2) return null;
            const d = pts.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x} ${p.y * 0.72 + 6}`).join(" ");
            return (
              <path
                key={net.name}
                d={d}
                fill="none"
                stroke="#e08a45"
                strokeWidth={net.name === "GND" ? 1.4 : 0.55}
                opacity={net.name === "GND" ? 0.35 : 0.9}
              />
            );
          })}
        {showParts &&
          pcb.parts.map((p) => (
            <g key={p.ref}>
              <rect
                x={p.x - p.w / 2}
                y={p.y * 0.72 + 6 - p.h / 2}
                width={p.w}
                height={p.h}
                rx="0.6"
                fill="#e7eef2"
                stroke="#8a5530"
                strokeWidth="0.3"
              />
              <text
                x={p.x}
                y={p.y * 0.72 + 7}
                textAnchor="middle"
                fontSize="2.4"
                fill="#1a1008"
                fontFamily="IBM Plex Mono, ui-monospace, monospace"
              >
                {p.ref}
              </text>
            </g>
          ))}
        {pcb.stage < 3 && (
          <text x="50" y="40" textAnchor="middle" fill="#8d9aa4" fontSize="3.2">
            {PCB_STAGES[pcb.stage]}
          </text>
        )}
      </svg>
    </div>
  );
}

export function CadView() {
  const cad = useSi((s) => s.cad);
  const patchCad = useSi((s) => s.patchCad);
  const mass = cadMassG(cad);
  const vol = cadVolumeCm3(cad);
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Panel kicker="CAD" title={cad.name}>
        <CadArt cad={cad} />
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          <Stat label="Volume" value={`${vol.toFixed(2)} cm³`} />
          <Stat label="Mass" value={`${mass.toFixed(1)} g`} />
          <Stat label="Material" value={cad.material} />
        </div>
      </Panel>
      <Panel kicker="Features" title="Sketch, extrude, hole, fillet">
        <Field label="Name">
          <input className={inputCls} value={cad.name} onChange={(e) => patchCad({ name: e.target.value })} />
        </Field>
        <div className="grid grid-cols-2 gap-2">
          <Num label="Length mm" value={cad.length} min={20} max={160} onChange={(length) => patchCad({ length })} />
          <Num label="Width mm" value={cad.width} min={12} max={120} onChange={(width) => patchCad({ width })} />
          <Num label="Thickness" value={cad.thickness} min={2} max={20} onChange={(thickness) => patchCad({ thickness })} />
          <Num label="Hole Ø" value={cad.hole} min={0} max={30} onChange={(hole) => patchCad({ hole })} />
          <Num label="Fillet R" value={cad.fillet} min={0} max={12} onChange={(fillet) => patchCad({ fillet })} />
          <Field label="Material">
            <select
              className={inputCls}
              value={cad.material}
              onChange={(e) => patchCad({ material: e.target.value as CadModel["material"] })}
            >
              {(["6061-T6", "316L", "PETG", "ABS"] as const).map((m) => (
                <option key={m}>{m}</option>
              ))}
            </select>
          </Field>
        </div>
        <ol className="flex flex-col gap-1 text-sm">
          {[
            `Sketch rectangle ${cad.length} × ${cad.width}`,
            `Extrude ${cad.thickness} mm`,
            cad.hole > 0 ? `Hole Ø${cad.hole} through` : "No hole",
            cad.fillet > 0 ? `Fillet R${cad.fillet}` : "Sharp edges",
          ].map((step, i) => (
            <li key={step} className="flex gap-2 rounded-md border border-line bg-bg px-3 py-2">
              <span className="font-mono text-xs text-copper">{i + 1}</span>
              {step}
            </li>
          ))}
        </ol>
        <pre className="overflow-x-auto rounded-md bg-bg p-3 font-mono text-xs text-muted">
{`# STEP feature script
solid ${cad.name.replace(/\s+/g, "_")}
  rect ${cad.length} ${cad.width}
  extrude ${cad.thickness}
  hole ${cad.hole} through
  fillet ${cad.fillet}
  material ${cad.material}
end`}
        </pre>
      </Panel>
    </div>
  );
}

function CadArt({ cad }: { cad: CadModel }) {
  const L = 46;
  const W = (cad.width / cad.length) * L;
  const T = Math.max(6, (cad.thickness / 8) * 16);
  const ox = 78;
  const oy = 78;
  const pt = (x: number, y: number, z: number) =>
    `${(ox + (x - y) * 0.9).toFixed(1)},${(oy + (x + y) * 0.45 - z).toFixed(1)}`;
  const top = [pt(0, 0, T), pt(L, 0, T), pt(L, W, T), pt(0, W, T)].join(" ");
  const front = [pt(0, 0, 0), pt(L, 0, 0), pt(L, 0, T), pt(0, 0, T)].join(" ");
  const side = [pt(L, 0, 0), pt(L, W, 0), pt(L, W, T), pt(L, 0, T)].join(" ");
  const hx = L / 2;
  const hy = W / 2;
  const hole = pt(hx, hy, T);
  const [cx, cy] = hole.split(",");
  const r = Math.max(2, (cad.hole / cad.length) * L * 0.45);
  return (
    <svg viewBox="0 0 200 130" className="h-48 w-full rounded-md border border-line bg-bg">
      <polygon points={front} fill="#2a241e" stroke="#e08a45" strokeWidth="0.8" />
      <polygon points={side} fill="#1c1916" stroke="#e08a45" strokeWidth="0.8" />
      <polygon points={top} fill="#e7eef2" stroke="#8a5530" strokeWidth="0.8" />
      {cad.hole > 0 && <circle cx={cx} cy={cy} r={r} fill="#0e1214" stroke="#e08a45" strokeWidth="0.6" />}
    </svg>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-line bg-bg px-3 py-2">
      <p className="text-xs text-muted">{label}</p>
      <p className="font-mono text-sm">{value}</p>
    </div>
  );
}

function Num({
  label,
  value,
  min,
  max,
  step = 1,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  onChange: (n: number) => void;
}) {
  return (
    <Field label={`${label} · ${value}`}>
      <input
        className="h-11 accent-copper"
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
      />
    </Field>
  );
}

export function CamView() {
  const cad = useSi((s) => s.cad);
  const cam = useSi((s) => s.cam);
  const adapter = useSi((s) => s.adapter);
  const patchCam = useSi((s) => s.patchCam);
  const gcode = camProgram(cad, cam, adapter);
  const feed = Math.round(cam.feed * adapter.camFeedScale);
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Panel kicker="CAM" title={`${cad.name} in ${cam.stock}`}>
        <Toolpath />
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          <Stat label="Feed" value={`${feed} mm/min`} />
          <Stat label="Spindle" value={`${cam.spindle} rpm`} />
          <Stat label="Tool" value={`Ø${cam.toolMm} mm`} />
        </div>
        <div className="grid grid-cols-2 gap-2">
          <Num label="Tool mm" value={cam.toolMm} min={1} max={12} onChange={(toolMm) => patchCam({ toolMm })} />
          <Num label="Feed" value={cam.feed} min={200} max={2000} step={50} onChange={(feedMm) => patchCam({ feed: feedMm })} />
          <Num label="Spindle" value={cam.spindle} min={4000} max={24000} step={500} onChange={(spindle) => patchCam({ spindle })} />
          <Num label="Stepdown" value={cam.stepdown} min={0.2} max={4} step={0.1} onChange={(stepdown) => patchCam({ stepdown })} />
        </div>
        <Field label="Stock">
          <select
            className={inputCls}
            value={cam.stock}
            onChange={(e) => patchCam({ stock: e.target.value as typeof cam.stock })}
          >
            <option value="aluminum">aluminum</option>
            <option value="abs">abs</option>
            <option value="delrin">delrin</option>
          </select>
        </Field>
      </Panel>
      <Panel kicker="G-code" title="Contour then bore">
        <pre className="max-h-96 overflow-auto rounded-md bg-bg p-3 font-mono text-xs leading-relaxed text-muted">
          {gcode}
        </pre>
      </Panel>
    </div>
  );
}

function Toolpath() {
  return (
    <svg viewBox="0 0 160 90" className="h-40 w-full rounded-md border border-line bg-bg">
      <rect x="18" y="14" width="120" height="60" fill="#1e262c" stroke="#2c3840" />
      <rect x="28" y="22" width="100" height="44" fill="none" stroke="#e08a45" strokeWidth="1.4" />
      <circle cx="78" cy="44" r="8" fill="none" stroke="#e08a45" strokeWidth="1.2" />
      <path d="M8 78 H150" stroke="#5c6b74" strokeWidth="0.4" />
      <text x="28" y="12" fill="#8d9aa4" fontSize="5" fontFamily="IBM Plex Mono, monospace">
        G1 contour · G2 hole
      </text>
    </svg>
  );
}

export function PrintView() {
  const cad = useSi((s) => s.cad);
  const print = useSi((s) => s.print);
  const patchPrint = useSi((s) => s.patchPrint);
  const plan = printPlan(print, cad);
  const [layer, setLayer] = useState(1);
  const shown = Math.min(layer, plan.layers);
  const hatch = Math.max(2, Math.round(4 + (100 - print.infill) / 12));
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Panel kicker="3D print" title={`${print.material} · ${cad.name}`}>
        <svg viewBox="0 0 160 120" className="h-52 w-full rounded-md border border-line bg-bg">
          <rect x="20" y="16" width="120" height="88" rx="2" fill="#12171a" stroke="#2c3840" />
          <rect x="46" y="36" width="68" height="40" fill="#1e262c" stroke="#e08a45" />
          {Array.from({ length: 8 }).map((_, i) =>
            i % hatch === 0 ? (
              <line
                key={i}
                x1={48}
                x2={112}
                y1={40 + i * 4}
                y2={40 + i * 4}
                stroke="#e08a45"
                strokeWidth="0.6"
                opacity={shown / plan.layers}
              />
            ) : null,
          )}
          {print.supports && (
            <>
              <line x1="46" y1="76" x2="40" y2="96" stroke="#8d9aa4" strokeWidth="0.6" />
              <line x1="114" y1="76" x2="120" y2="96" stroke="#8d9aa4" strokeWidth="0.6" />
            </>
          )}
          <text x="24" y="14" fill="#8d9aa4" fontSize="5" fontFamily="IBM Plex Mono, monospace">
            {`layer ${shown}/${plan.layers}`}
          </text>
        </svg>
        <Field label={`Preview layer ${shown}`}>
          <input
            className="h-11 accent-copper"
            type="range"
            min={1}
            max={plan.layers}
            value={shown}
            onChange={(e) => setLayer(Number(e.target.value))}
          />
        </Field>
      </Panel>
      <Panel kicker="Slice" title="Time and filament">
        <div className="grid grid-cols-3 gap-2">
          <Stat label="Mass" value={`${plan.grams.toFixed(1)} g`} />
          <Stat label="Time" value={`${plan.minutes} min`} />
          <Stat label="Layers" value={String(plan.layers)} />
        </div>
        <div className="grid grid-cols-2 gap-2">
          <Field label="Material">
            <select
              className={inputCls}
              value={print.material}
              onChange={(e) => patchPrint({ material: e.target.value as typeof print.material })}
            >
              {(["PLA", "PETG", "ABS", "Resin"] as const).map((m) => (
                <option key={m}>{m}</option>
              ))}
            </select>
          </Field>
          <Num label="Bed mm" value={print.bed} min={120} max={350} step={10} onChange={(bed) => patchPrint({ bed })} />
          <Num label="Nozzle" value={print.nozzle} min={0.2} max={0.8} step={0.1} onChange={(nozzle) => patchPrint({ nozzle })} />
          <Num label="Layer mm" value={print.layer} min={0.08} max={0.32} step={0.04} onChange={(layerH) => patchPrint({ layer: layerH })} />
          <Num label="Infill %" value={print.infill} min={0} max={100} step={5} onChange={(infill) => patchPrint({ infill })} />
          <Num label="Walls" value={print.walls} min={1} max={6} onChange={(walls) => patchPrint({ walls })} />
        </div>
        <button
          type="button"
          className={
            "h-11 rounded-md border px-3 text-sm " +
            (print.supports ? "border-copper bg-copper text-copper-ink" : "border-line bg-bg")
          }
          onClick={() => patchPrint({ supports: !print.supports })}
        >
          Supports {print.supports ? "on" : "off"}
        </button>
      </Panel>
    </div>
  );
}

export function SimView() {
  const kind = useSi((s) => s.simKind);
  const setSimKind = useSi((s) => s.setSimKind);
  const cad = useSi((s) => s.cad);
  const adapter = useSi((s) => s.adapter);
  const data = simSeries(kind, cad, adapter);
  const over = data.some((p) => (kind === "signal" ? p.value < p.limit : p.value > p.limit));
  const unit = kind === "thermal" ? "°C" : kind === "stress" ? "MPa" : "dB";
  const title = kind === "thermal" ? "Junction rise" : kind === "stress" ? "Von Mises vs load" : "Insertion loss";
  return (
    <Panel
      kicker="Simulation"
      title={title}
      action={
        <div className="flex gap-1">
          {(["thermal", "stress", "signal"] as const).map((k) => (
            <button
              key={k}
              type="button"
              onClick={() => setSimKind(k)}
              className={
                "h-11 rounded-md border px-3 text-xs capitalize " +
                (kind === k ? "border-copper bg-copper text-copper-ink" : "border-line text-muted")
              }
            >
              {k}
            </button>
          ))}
        </div>
      }
    >
      <p className="text-sm text-muted">
        {cad.name}, {cad.material}, safety {adapter.safety.toFixed(1)}.{" "}
        {over ? "A sample crosses the limit." : "Inside the limit for this case."}
      </p>
      <div className="h-64 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data}>
            <CartesianGrid stroke="#2c3840" strokeDasharray="3 3" />
            <XAxis dataKey="step" stroke="#8d9aa4" fontSize={11} />
            <YAxis stroke="#8d9aa4" fontSize={11} unit={unit === "dB" ? "" : ""} />
            <Tooltip contentStyle={tipStyle} />
            <Line type="monotone" dataKey="value" name={unit} stroke="#e08a45" strokeWidth={2} dot={false} />
            <Line type="monotone" dataKey="limit" name="limit" stroke="#8d9aa4" strokeDasharray="4 4" dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </Panel>
  );
}

export function TrainView() {
  const learned = useSi((s) => s.learned);
  const learn = useSi((s) => s.learn);
  const learnNote = useSi((s) => s.learnNote);
  const adapter = useSi((s) => s.adapter);
  const [note, setNote] = useState("");
  const [epoch, setEpoch] = useState(0);
  const [running, setRunning] = useState<string | null>(null);

  useEffect(() => {
    if (!running) return;
    if (epoch >= 6) {
      if (running === "note") learnNote(note);
      else learn(running);
      setRunning(null);
      setEpoch(0);
      setNote("");
      return;
    }
    const t = window.setTimeout(() => setEpoch((e) => e + 1), 220);
    return () => window.clearTimeout(t);
  }, [running, epoch, learn, learnNote, note]);

  return (
    <div className="grid gap-4 lg:grid-cols-5">
      <Panel kicker="Train" title="Lessons that move the adapter" action={<Epoch epoch={running ? epoch : 0} />}>
        <ul className="flex flex-col gap-2 lg:col-span-3">
          {LIBRARY.map((lesson) => {
            const on = learned.includes(lesson.id);
            return (
              <li key={lesson.id} className="flex flex-col gap-2 rounded-md border border-line bg-bg p-3 sm:flex-row sm:items-center">
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium">{lesson.title}</p>
                  <p className="text-xs text-muted">{lesson.note}</p>
                </div>
                <button
                  type="button"
                  disabled={on || running !== null}
                  onClick={() => {
                    setEpoch(0);
                    setRunning(lesson.id);
                  }}
                  className="h-11 shrink-0 rounded-md bg-copper px-3 text-sm font-medium text-copper-ink disabled:opacity-40"
                >
                  {on ? "In adapter" : "Improve"}
                </button>
              </li>
            );
          })}
        </ul>
      </Panel>
      <div className="flex flex-col gap-4 lg:col-span-2">
        <Panel kicker="Adapter" title="What the next run uses">
          <Stat label="Clearance" value={`${adapter.clearanceMm.toFixed(2)} mm`} />
          <Stat label="Trace" value={`${adapter.traceMm.toFixed(2)} mm`} />
          <Stat label="Safety" value={adapter.safety.toFixed(1)} />
          <Stat label="Print bias" value={adapter.printMaterial} />
          <Stat label="Feed scale" value={adapter.camFeedScale.toFixed(2)} />
        </Panel>
        <Panel kicker="Your note" title="Teach a preference">
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Prefer PETG for brackets, or open clearance to 0.2 mm"
            className="min-h-24 rounded-md border border-line bg-bg p-3 text-sm outline-none focus:border-copper"
          />
          <button
            type="button"
            disabled={!note.trim() || running !== null}
            onClick={() => {
              setEpoch(0);
              setRunning("note");
            }}
            className="h-11 rounded-md border border-copper px-3 text-sm text-copper disabled:opacity-40"
          >
            Run improvement
          </button>
        </Panel>
      </div>
    </div>
  );
}

function Epoch({ epoch }: { epoch: number }) {
  return (
    <span className="font-mono text-xs text-muted">
      epoch {epoch}/6
    </span>
  );
}

export function AnalyzeView() {
  const turns = useSi((s) => s.turns);
  const rate = useSi((s) => s.rate);
  const pcb = useSi((s) => s.pcb);
  const adapter = useSi((s) => s.adapter);
  const board = scoreboard(turns);
  const data = (["pcb", "cad", "cam", "print", "sim"] as Domain[]).map((d) => ({
    desk: d.toUpperCase(),
    score: Number(board[d].avg.toFixed(2)),
    n: board[d].n,
  }));
  const last = [...turns].reverse().find((t) => t.role === "si" && t.id !== "welcome");
  const pass = pcb.drc.filter((d) => d.status === "pass").length;
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Panel kicker="Analyze" title="Scores you gave the model">
        <div className="h-56">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data}>
              <CartesianGrid stroke="#2c3840" vertical={false} />
              <XAxis dataKey="desk" stroke="#8d9aa4" fontSize={11} />
              <YAxis domain={[0, 5]} stroke="#8d9aa4" fontSize={11} />
              <Tooltip contentStyle={tipStyle} />
              <Bar dataKey="score" fill="#e08a45" radius={4} />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <p className="text-xs text-muted">
          {board.total} rated replies. DRC {pass}/{pcb.drc.length} passing on {pcb.title}. Adapter lessons{" "}
          {adapter.lessons}.
        </p>
      </Panel>
      <Panel kicker="Grade" title="Last specialist reply">
        {last ? (
          <>
            <p className="text-sm text-muted">{last.text}</p>
            <div className="flex gap-1">
              {[1, 2, 3, 4, 5].map((n) => (
                <button
                  key={n}
                  type="button"
                  onClick={() => rate(last.id, n)}
                  className={
                    "h-11 w-11 rounded-md border text-sm " +
                    ((last.stars ?? 0) >= n
                      ? "border-copper bg-copper text-copper-ink"
                      : "border-line text-muted")
                  }
                >
                  {n}
                </button>
              ))}
            </div>
          </>
        ) : (
          <p className="text-sm text-muted">Send a prompt, then score the reply. Scores stay on this device.</p>
        )}
      </Panel>
    </div>
  );
}
