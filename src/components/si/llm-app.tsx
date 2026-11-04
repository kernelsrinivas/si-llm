import { useEffect, useRef, useState } from "react";
import { useServerFn } from "@tanstack/react-start";
import { addMcp, approveCall, askModel, modelHealth, removeMcp, setMode, uploadDatasheet, type McpLink, type RunMode, type Snapshot, type ToolCall } from "@/lib/si/run";

type Part = { ref: string; pkg: string; x: number; y: number };
type Net = { name: string; a: string; b: string };
type Drc = { rule: string; status: string; detail: string };
type Cad = {
  length: number | null;
  width: number | null;
  thickness: number | null;
  hole: number;
  fillet: number;
};
type Msg = {
  id: string;
  role: "you" | "si";
  text: string;
  command?: string;
  runtime?: string;
  proposalId?: string;
  calls?: ToolCall[];
};

const MODES: { id: RunMode; label: string; hint: string }[] = [
  { id: "auto", label: "Auto", hint: "Auto runs every tool call." },
  { id: "semi", label: "Semi", hint: "Semi asks only when the board or the solid changes." },
  { id: "man", label: "Man", hint: "Man asks before every tool call." },
];
const PROMPTS = [
  "Handle all industries",
  "Set the board outline 305 by 244",
  "Automatic industry",
  "Aerospace industry",
  "Marine industry",
  "Robot industry",
  "Medical industry",
  "Tiny circuit",
  "Power electronics",
  "BMS board",
  "Motor control",
  "CPU motherboard",
  "GPU board",
  "Network modem",
  "Large motherboard",
  "Check the industry rules",
  "Build from the datasheet",
  "50 ohm trace",
  "Size the via for 2 A",
  "DFM check",
  "IPC check",
  "Set IPC class 3",
];

export function LlmApp() {
  const ask = useServerFn(askModel);
  const upload = useServerFn(uploadDatasheet);
  const health = useServerFn(modelHealth);
  const connect = useServerFn(addMcp);
  const disconnect = useServerFn(removeMcp);
  const approve = useServerFn(approveCall);
  const chooseMode = useServerFn(setMode);
  const [text, setText] = useState("");
  const [cli, setCli] = useState("pcb status");
  const [linkName, setLinkName] = useState("");
  const [linkKind, setLinkKind] = useState<"http" | "stdio">("http");
  const [linkTarget, setLinkTarget] = useState("");
  const [linkError, setLinkError] = useState("");
  const [msgs, setMsgs] = useState<Msg[]>([
    {
      id: "hi",
      role: "si",
      text: "Pick Auto, Semi, or Man. Auto runs the call. Semi asks only when the design changes. Man asks every time.",
    },
  ]);
  const [snap, setSnap] = useState<Snapshot | null>(null);
  const [meta, setMeta] = useState<string>("starting");
  const [busy, setBusy] = useState(false);
  const [servers, setServers] = useState<McpLink[]>([]);
  const [mode, setRunMode] = useState<RunMode>("man");
  const logRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    void health().then((res) => {
      if (!res.ok) {
        setMeta("offline");
        return;
      }
      const pct = `${Math.round(res.heldout * 1000) / 10}% held-out`;
      const params =
        res.params >= 1_000_000
          ? `${(res.params / 1_000_000).toFixed(1)}M params`
          : res.params
            ? `${Math.round(res.params / 1000)}k params`
            : "";
      setMeta(`pytorch · ${pct}${params ? ` · ${params}` : ""}`);
      setServers(res.servers);
      setRunMode(res.mode);
      setSnap(res.state);
    });
  }, [health]);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight });
  }, [msgs.length]);

  async function send(line: string) {
    const clean = line.trim();
    if (!clean || busy) return;
    setBusy(true);
    setMsgs((m) => [...m, { id: rid(), role: "you", text: clean }]);
    setText("");
    try {
      const res = await ask({ data: { text: clean } });
      if (!res.ok) {
        setMsgs((m) => [...m, { id: rid(), role: "si", text: res.error }]);
        return;
      }
      setMsgs((m) => [
        ...m,
        {
          id: rid(),
          role: "si",
          text: res.reply,
          command: res.needsApproval ? undefined : res.commands[0],
          runtime: res.runtime,
          proposalId: res.needsApproval ? res.proposalId : undefined,
          calls: res.needsApproval ? res.calls : undefined,
        },
      ]);
      if (!res.needsApproval) setSnap(res.state);
    } catch {
      setMsgs((m) => [...m, { id: rid(), role: "si", text: "The model server did not answer." }]);
    } finally {
      setBusy(false);
    }
  }

  async function onDatasheet(file: File) {
    if (busy) return;
    setBusy(true);
    setMsgs((m) => [...m, { id: rid(), role: "you", text: `Datasheet ${file.name}` }]);
    try {
      const pdf = file.name.toLowerCase().endsWith(".pdf") ? await fileToBase64(file) : "";
      const text = pdf ? "" : await file.text();
      const res = await upload({ data: { name: file.name, text, pdf } });
      if (!res.ok) {
        setMsgs((m) => [...m, { id: rid(), role: "si", text: res.error }]);
        return;
      }
      setMsgs((m) => [
        ...m,
        {
          id: rid(),
          role: "si",
          text: res.reply,
          command: res.needsApproval ? undefined : res.commands[0],
          runtime: res.runtime,
          proposalId: res.needsApproval ? res.proposalId : undefined,
          calls: res.needsApproval ? res.calls : undefined,
        },
      ]);
      if (!res.needsApproval) setSnap(res.state);
    } catch {
      setMsgs((m) => [...m, { id: rid(), role: "si", text: "The datasheet could not be read." }]);
    } finally {
      if (fileRef.current) fileRef.current.value = "";
      setBusy(false);
    }
  }

  async function onDecide(msgId: string, proposalId: string, decision: "allow" | "always" | "deny") {
    setBusy(true);
    try {
      const res = await approve({ data: { proposalId, decision } });
      if (!res.ok) {
        setMsgs((m) => m.map((msg) => (msg.id === msgId ? { ...msg, text: res.error, proposalId: undefined } : msg)));
        return;
      }
      setMsgs((m) =>
        m.map((msg) =>
          msg.id === msgId
            ? { ...msg, text: res.reply, command: res.commands[0], runtime: res.runtime, proposalId: undefined }
            : msg,
        ),
      );
      setSnap(res.state);
    } catch {
      setMsgs((m) => m.map((msg) => (msg.id === msgId ? { ...msg, text: "The approval did not go through.", proposalId: undefined } : msg)));
    } finally {
      setBusy(false);
    }
  }

  async function onConnect(preset?: "pcb" | "cad") {
    setLinkError("");
    setBusy(true);
    try {
      const res = preset
        ? await connect({ data: { preset, name: "", transport: "http", target: "" } })
        : await connect({ data: { preset: "", name: linkName, transport: linkKind, target: linkTarget } });
      if (!res.ok) {
        setLinkError(res.error);
        return;
      }
      setServers(res.servers);
      setLinkName("");
      setLinkTarget("");
    } catch {
      setLinkError("Could not connect.");
    } finally {
      setBusy(false);
    }
  }

  async function onMode(next: RunMode) {
    setRunMode(next);
    const res = await chooseMode({ data: { mode: next } });
    if (!res.ok) setLinkError(res.error);
    else setRunMode(res.mode);
  }

  async function onRemove(name: string) {
    setBusy(true);
    try {
      const res = await disconnect({ data: { name } });
      if (res.ok) setServers(res.servers);
      else setLinkError(res.error);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex h-dvh min-w-0 flex-col overflow-x-hidden bg-bg text-fg">
      <header className="flex min-w-0 items-center justify-between gap-3 border-b border-line px-3 py-2 sm:px-4">
        <div className="flex items-center gap-3">
          <span className="grid h-9 w-9 place-items-center rounded-md bg-copper font-mono text-xs font-medium text-copper-ink">
            SI
          </span>
          <div>
            <p className="text-sm font-semibold tracking-tight">SI-LLM</p>
            <p className="text-xs text-muted">PCB and CAD specialist</p>
          </div>
        </div>
        <p className="min-w-0 truncate font-mono text-xs text-copper">{meta}</p>
      </header>

      <section className="flex min-w-0 flex-col gap-2 border-b border-line px-3 py-2 sm:px-4">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <p className="font-mono text-xs tracking-wide text-copper uppercase">MCP</p>
          <div className="flex overflow-hidden rounded-md border border-line">
            {MODES.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => void onMode(item.id)}
                className={
                  "h-9 px-3 text-xs " +
                  (mode === item.id ? "bg-copper font-medium text-copper-ink" : "text-muted")
                }
              >
                {item.label}
              </button>
            ))}
          </div>
          <p className="text-xs text-muted">{MODES.find((item) => item.id === mode)?.hint}</p>
        </div>
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          {servers.map((server) => (
            <span key={server.id} className="inline-flex items-center gap-2 rounded-md border border-line bg-surface px-2 py-1 text-xs">
              <span className={server.ok ? "text-fg" : "text-muted"}>
                {server.title} {server.ok ? "connected" : "offline"}
              </span>
              <button type="button" onClick={() => void onRemove(server.id)} className="text-muted hover:text-fg">
                Remove
              </button>
            </span>
          ))}
          {!servers.some((server) => server.id === "pcb") && (
            <button type="button" disabled={busy} onClick={() => void onConnect("pcb")} className="h-9 rounded-md border border-line px-3 text-xs disabled:opacity-40">
              Connect PCB
            </button>
          )}
          {!servers.some((server) => server.id === "cad") && (
            <button type="button" disabled={busy} onClick={() => void onConnect("cad")} className="h-9 rounded-md border border-line px-3 text-xs disabled:opacity-40">
              Connect CAD
            </button>
          )}
          {!servers.length && <span className="text-xs text-muted">No connection yet.</span>}
        </div>
        <form
          className="flex min-w-0 flex-wrap gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            void onConnect();
          }}
        >
          <input
            value={linkName}
            onChange={(e) => setLinkName(e.target.value)}
            placeholder="name"
            className="h-11 w-28 rounded-md border border-line bg-surface px-2 text-sm outline-none focus:border-copper"
          />
          <select
            value={linkKind}
            onChange={(e) => setLinkKind(e.target.value === "stdio" ? "stdio" : "http")}
            className="h-11 rounded-md border border-line bg-surface px-2 text-sm"
          >
            <option value="http">URL</option>
            <option value="stdio">Command</option>
          </select>
          <input
            value={linkTarget}
            onChange={(e) => setLinkTarget(e.target.value)}
            placeholder={linkKind === "http" ? "MCP server URL" : "MCP server command"}
            className="h-11 min-w-0 flex-1 rounded-md border border-line bg-surface px-3 text-sm outline-none focus:border-copper"
          />
          <button type="submit" disabled={busy} className="h-11 rounded-md border border-line px-3 text-sm disabled:opacity-40">
            Add
          </button>
        </form>
        {linkError && <p className="text-xs text-muted">{linkError}</p>}
      </section>

      <div className="grid min-h-0 min-w-0 flex-1 lg:grid-cols-[minmax(0,1fr)_340px]">
        <div className="flex min-h-0 min-w-0 flex-col">
          <div ref={logRef} className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto p-3 sm:p-4">
            {msgs.map((msg) => (
              <article key={msg.id} className={msg.role === "you" ? "max-w-xl self-end" : "max-w-xl self-start"}>
                <p className="mb-1 font-mono text-xs text-faint">{msg.role === "you" ? "You" : "SI-LLM"}</p>
                <p className={"rounded-lg px-3 py-2 text-sm break-words " + (msg.role === "you" ? "bg-raised" : "border border-line bg-surface")}>
                  {msg.text}
                </p>
                {msg.proposalId && msg.calls && (
                  <div className="mt-2 rounded-lg border border-copper bg-surface p-3">
                    {msg.calls.map((call) => (
                      <div key={call.server + call.tool} className="mb-2">
                        <p className="font-mono text-xs text-copper">
                          {call.server} · {call.tool}
                        </p>
                        {call.args.map((arg) => (
                          <p key={arg.key} className="font-mono text-xs text-muted">
                            {arg.key} {arg.value}
                          </p>
                        ))}
                      </div>
                    ))}
                    <div className="flex flex-wrap gap-2">
                      <button type="button" disabled={busy} onClick={() => void onDecide(msg.id, msg.proposalId || "", "allow")} className="h-9 rounded-md bg-copper px-3 text-xs font-medium text-copper-ink disabled:opacity-40">
                        Allow once
                      </button>
                      <button type="button" disabled={busy} onClick={() => void onDecide(msg.id, msg.proposalId || "", "always")} className="h-9 rounded-md border border-line px-3 text-xs disabled:opacity-40">
                        Always allow
                      </button>
                      <button type="button" disabled={busy} onClick={() => void onDecide(msg.id, msg.proposalId || "", "deny")} className="h-9 rounded-md border border-line px-3 text-xs text-muted disabled:opacity-40">
                        Deny
                      </button>
                    </div>
                  </div>
                )}
                {msg.command && (
                  <p className="mt-1 font-mono text-xs break-all text-copper">
                    {msg.runtime} · {msg.command}
                  </p>
                )}
              </article>
            ))}
          </div>
          <div className="flex min-w-0 gap-2 overflow-x-auto border-t border-line px-3 py-2">
            {PROMPTS.map((p) => (
              <button
                key={p}
                type="button"
                onClick={() => void send(p)}
                className="h-10 shrink-0 rounded-md border border-line px-3 text-xs text-muted hover:border-copper hover:text-fg"
              >
                {p}
              </button>
            ))}
          </div>
          <form
            className="flex gap-2 px-3 pb-3 sm:px-4"
            onSubmit={(e) => {
              e.preventDefault();
              void send(text);
            }}
          >
            <input
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Place a part, tie a net, sketch a plate…"
              className="h-11 min-w-0 flex-1 rounded-md border border-line bg-surface px-3 text-sm outline-none focus:border-copper"
            />
            <button type="submit" disabled={busy} className="h-11 rounded-md bg-copper px-4 text-sm font-medium text-copper-ink disabled:opacity-40">
              {busy ? "…" : "Send"}
            </button>
            <button type="button" disabled={busy} onClick={() => fileRef.current?.click()} className="h-11 rounded-md border border-line px-3 text-sm disabled:opacity-40">
              Datasheet
            </button>
            <input
              ref={fileRef}
              type="file"
              accept=".txt,.md,.pdf,text/plain,application/pdf"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) void onDatasheet(file);
              }}
            />
          </form>
        </div>

        <aside className="flex min-h-0 flex-col gap-3 overflow-y-auto border-t border-line p-3 lg:border-t-0 lg:border-l">
          <Flow snap={snap} />
          <Sheets snap={snap} />
          <Board snap={snap} />
          <Solid snap={snap} />
          <section className="rounded-lg border border-line bg-surface p-3">
            <p className="font-mono text-xs tracking-wide text-copper uppercase">CLI</p>
            <form
              className="mt-2 flex gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                void send(cli);
              }}
            >
              <input
                value={cli}
                onChange={(e) => setCli(e.target.value)}
                className="h-11 min-w-0 flex-1 rounded-md border border-line bg-bg px-2 font-mono text-xs outline-none focus:border-copper"
              />
              <button type="submit" className="h-11 rounded-md border border-line px-3 text-xs">
                Run
              </button>
            </form>
            <p className="mt-2 text-xs break-all text-muted">pcb add --ref U1 --pkg ESP32 --x 40 --y 30</p>
          </section>
        </aside>
      </div>
    </div>
  );
}

function rid() {
  return Math.random().toString(36).slice(2, 10);
}

async function fileToBase64(file: File) {
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = "";
  for (let i = 0; i < bytes.length; i += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  }
  return btoa(binary);
}

function Flow({ snap }: { snap: Snapshot | null }) {
  const work = snap?.work;
  const boardName: Record<string, string> = {
    tiny: "Tiny circuit",
    power: "Power electronics",
    bms: "BMS",
    motor: "Motor control",
    cpu: "CPU motherboard",
    gpu: "GPU board",
    modem: "Network modem",
    motherboard: "Large motherboard",
  };
  const industry = work?.industry ? work.industry[0].toUpperCase() + work.industry.slice(1) : "Not set";
  const board = work?.board ? boardName[work.board] || work.board : "Not set";
  const stages = [
    ["Industry", industry],
    ["Board", board],
    ["Outline", work?.outline.length === 2 ? `${work.outline[0]} × ${work.outline[1]} mm` : "Not set"],
    ["Schematic", work?.symbols.length ? `${work.symbols.length} symbols` : "Empty"],
    ["Layout", snap?.pcb.parts.length ? `${snap.pcb.parts.length} parts` : "Empty"],
    ["Footprint", work?.footprints.length ? `${work.footprints.length} assigned` : "Empty"],
    ["Simulation", work?.sim || "Empty"],
    ["3D viewer", work?.view3d || "Empty"],
    ["Design check", snap?.drc.length ? snap.drc.map((item) => `${item.rule} ${item.status}`).join(", ") : "Empty"],
    ["Fabrication", work?.fab || work?.stack || "Empty"],
    ["Signal", work?.signal || "Empty"],
    ["IPC", work?.ipc.length ? `Class ${work.ipcClass || "2"} · ${work.ipc.filter((item) => item.status === "pass").length}/${work.ipc.length}` : "Not run"],
    ["Assembly", work?.assembly || "Empty"],
  ];
  return (
    <section className="rounded-lg border border-line bg-surface p-3">
      <p className="font-mono text-xs tracking-wide text-copper uppercase">PCB flow</p>
      <ul className="mt-2 flex flex-col gap-1">
        {stages.map(([name, detail]) => (
          <li key={name} className="text-xs break-words text-muted">
            <span className="font-mono text-fg">{name}</span> {detail}
          </li>
        ))}
      </ul>
      {!!work?.ipc.length && (
        <ul className="mt-2 flex max-h-40 flex-col gap-1 overflow-y-auto border-t border-line pt-2">
          {work.ipc.map((item) => (
            <li key={item.name} className="text-xs break-words text-muted">
              <span className="font-mono text-fg">{item.name}</span> {item.status}
            </li>
          ))}
        </ul>
      )}
      {!!work?.chip.length && (
        <ul className="mt-2 flex flex-col gap-1 border-t border-line pt-2">
          {work.chip.map((item) => (
            <li key={item.name} className="text-xs break-words text-muted">
              <span className="font-mono text-copper">{item.status}</span> {item.name} — {item.detail}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function Sheets({ snap }: { snap: Snapshot | null }) {
  const rows = snap?.work.datasheets ?? [];
  return (
    <section className="rounded-lg border border-line bg-surface p-3">
      <p className="font-mono text-xs tracking-wide text-copper uppercase">Datasheet</p>
      {!rows.length && <p className="mt-2 text-xs text-muted">Upload a part datasheet. Every package that has a body size becomes a symbol, a calculated footprint, a placement, and a 3D body.</p>}
      <ul className="mt-2 flex flex-col gap-1">
        {rows.map((row) => (
          <li key={row.ref} className="text-xs break-words text-muted">
            <span className="font-mono text-copper">{row.ref}</span> {row.mpn} {row.package} · {row.pins} pads · {row.body} · {row.land} · {row.nets}
          </li>
        ))}
      </ul>
    </section>
  );
}

function Board({ snap }: { snap: Snapshot | null }) {
  const parts = snap?.pcb.parts ?? [];
  const nets = snap?.pcb.nets ?? [];
  return (
    <section className="rounded-lg border border-line bg-surface p-3">
      <p className="font-mono text-xs tracking-wide text-copper uppercase">PCB</p>
      <svg viewBox="0 0 100 72" className="mt-2 h-36 w-full rounded-md bg-bg">
        <rect x="4" y="4" width="92" height="64" rx="2" fill="#14110e" stroke="#e08a45" strokeWidth="0.6" />
        {nets.map((net) => {
          const a = parts.find((p) => p.ref === net.a);
          const b = parts.find((p) => p.ref === net.b);
          if (!a || !b) return null;
          return (
            <line
              key={net.name + net.a + net.b}
              x1={6 + a.x}
              y1={8 + a.y * 0.7}
              x2={6 + b.x}
              y2={8 + b.y * 0.7}
              stroke="#e08a45"
              strokeWidth="0.7"
            />
          );
        })}
        {parts.map((p) => (
          <g key={p.ref}>
            <rect x={4 + p.x} y={6 + p.y * 0.7} width="10" height="7" rx="0.6" fill="#e7eef2" />
            <text x={9 + p.x} y={11 + p.y * 0.7} textAnchor="middle" fontSize="2.4" fill="#1a1008">
              {p.ref}
            </text>
          </g>
        ))}
      </svg>
      <ul className="mt-2 flex flex-col gap-1">
        {(snap?.work.coverage.length ? snap.work.coverage : []).map((item) => (
          <li key={item.group + item.name} className="text-xs break-words text-muted">
            <span className="font-mono text-copper">{item.status}</span> {item.name} — {item.detail}
          </li>
        ))}
        {(snap?.drc ?? []).map((d) => (
          <li key={d.rule} className="text-xs text-muted">
            <span className="font-mono text-copper">{d.status}</span> {d.rule} — {d.detail}
          </li>
        ))}
        {!snap?.work.coverage.length && !snap?.drc.length && <li className="text-xs text-muted">No board yet.</li>}
      </ul>
    </section>
  );
}

function Solid({ snap }: { snap: Snapshot | null }) {
  const cad = snap?.cad;
  const sketched = cad?.length != null && cad.width != null;
  const l = sketched ? 50 : 36;
  const w = sketched ? Math.max(16, (Number(cad?.width) / Number(cad?.length)) * 50) : 24;
  const t = cad?.thickness ? Math.max(6, Math.min(18, Number(cad.thickness))) : 0;
  return (
    <section className="rounded-lg border border-line bg-surface p-3">
      <p className="font-mono text-xs tracking-wide text-copper uppercase">CAD</p>
      <svg viewBox="0 0 160 90" className="mt-2 h-28 w-full rounded-md bg-bg">
        {sketched ? (
          <>
            <polygon points={iso(20, 30, t, l, w)} fill="#e7eef2" stroke="#8a5530" />
            {t > 0 && <polygon points={front(20, 30, t, l)} fill="#2a241e" stroke="#e08a45" />}
          </>
        ) : (
          <text x="80" y="48" textAnchor="middle" fill="#8d9aa4" fontSize="8">
            No solid
          </text>
        )}
      </svg>
      <p className="text-xs text-muted">
        {snap?.mass
          ? `${snap.mass.grams} g · ${snap.mass.cm3} cm³ · 6061-T6`
          : sketched
            ? "Sketch is open. Extrude to get a mass."
            : "Sketch a plate to start the solid."}
      </p>
    </section>
  );
}

function iso(x: number, y: number, z: number, l: number, w: number) {
  const p = (px: number, py: number, pz: number) => `${x + (px - py) * 0.8},${y + (px + py) * 0.4 - pz}`;
  return [p(0, 0, z), p(l, 0, z), p(l, w, z), p(0, w, z)].join(" ");
}

function front(x: number, y: number, z: number, l: number) {
  const p = (px: number, py: number, pz: number) => `${x + (px - py) * 0.8},${y + (px + py) * 0.4 - pz}`;
  return [p(0, 0, 0), p(l, 0, 0), p(l, 0, z), p(0, 0, z)].join(" ");
}
