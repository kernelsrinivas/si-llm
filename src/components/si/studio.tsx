import { useEffect, useRef, useState } from "react";
import { useServerFn } from "@tanstack/react-start";
import {
  Activity,
  AudioLines,
  BarChart3,
  Box,
  CircuitBoard,
  Eye,
  GraduationCap,
  Mic,
  Printer,
  Settings2,
  Type,
} from "lucide-react";
import { deepen } from "@/lib/si/ask";
import { readVision, type Domain, type VisionRead } from "@/lib/si/model";
import { useSi, type Desk } from "@/lib/si/store";
import {
  AnalyzeView,
  BriefView,
  CadView,
  CamView,
  PcbView,
  PrintView,
  SimView,
  TrainView,
} from "./views";

const NAV: { id: Desk; label: string; icon: typeof Box }[] = [
  { id: "brief", label: "Studio", icon: AudioLines },
  { id: "pcb", label: "PCB", icon: CircuitBoard },
  { id: "cad", label: "CAD", icon: Box },
  { id: "cam", label: "CAM", icon: Settings2 },
  { id: "print", label: "Print", icon: Printer },
  { id: "sim", label: "Sim", icon: Activity },
  { id: "train", label: "Train", icon: GraduationCap },
  { id: "analyze", label: "Analyze", icon: BarChart3 },
];

type Rec = {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  onresult: ((ev: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null;
  onerror: (() => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
};

function recognition(): Rec | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as {
    SpeechRecognition?: new () => Rec;
    webkitSpeechRecognition?: new () => Rec;
  };
  const Ctor = w.SpeechRecognition ?? w.webkitSpeechRecognition;
  if (!Ctor) return null;
  const rec = new Ctor();
  rec.lang = "en-US";
  rec.interimResults = false;
  rec.continuous = false;
  return rec;
}

export function Studio() {
  const desk = useSi((s) => s.desk);
  const setDesk = useSi((s) => s.setDesk);
  const modality = useSi((s) => s.modality);
  const setModality = useSi((s) => s.setModality);
  const draft = useSi((s) => s.draft);
  const setDraft = useSi((s) => s.setDraft);
  const turns = useSi((s) => s.turns);
  const send = useSi((s) => s.send);
  const rate = useSi((s) => s.rate);
  const vision = useSi((s) => s.vision);
  const setVision = useSi((s) => s.setVision);
  const adapter = useSi((s) => s.adapter);
  const pcb = useSi((s) => s.pcb);
  const [ready, setReady] = useState(false);
  const [listening, setListening] = useState(false);
  const [voiceNote, setVoiceNote] = useState<string | null>(null);
  const [core, setCore] = useState<string | null>(null);
  const [coreErr, setCoreErr] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [logOpen, setLogOpen] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const logRef = useRef<HTMLDivElement>(null);
  const ask = useServerFn(deepen);

  useEffect(() => {
    void useSi.persist.rehydrate();
    setReady(true);
  }, []);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight });
  }, [turns.length, core]);

  function speak(text: string) {
    if (typeof window === "undefined" || !window.speechSynthesis) return;
    window.speechSynthesis.cancel();
    const utter = new SpeechSynthesisUtterance(text.slice(0, 420));
    utter.rate = 1;
    window.speechSynthesis.speak(utter);
  }

  function submit(mode?: "text" | "voice" | "vision") {
    const text = send(mode);
    setCore(null);
    setCoreErr(null);
    if (text && (mode ?? modality) === "voice") speak(text);
  }

  function listen() {
    const rec = recognition();
    if (!rec) {
      setVoiceNote("This browser has no speech recognition. Type, and I can still read the reply aloud.");
      setModality("voice");
      return;
    }
    setVoiceNote(null);
    setModality("voice");
    setListening(true);
    rec.onresult = (ev) => {
      const said = ev.results[0]?.[0]?.transcript ?? "";
      setDraft(said);
      setListening(false);
    };
    rec.onerror = () => {
      setListening(false);
      setVoiceNote("Mic did not return audio. Check permission, or type the brief.");
    };
    rec.onend = () => setListening(false);
    try {
      rec.start();
    } catch {
      setListening(false);
      setVoiceNote("Mic is already in use.");
    }
  }

  async function onFile(file: File | undefined) {
    if (!file) return;
    setModality("vision");
    const bmp = await createImageBitmap(file);
    const canvas = document.createElement("canvas");
    canvas.width = 48;
    canvas.height = 48;
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    if (!ctx) return;
    ctx.drawImage(bmp, 0, 0, 48, 48);
    const pixels = ctx.getImageData(0, 0, 48, 48).data;
    setVision(readVision(file.name, pixels));
    bmp.close?.();
  }

  function relabel(label: Domain) {
    if (!vision) return;
    setVision({ ...vision, label, note: `You labeled this ${label}. That correction is a training example.` });
  }

  async function deepenLast() {
    const lastYou = [...turns].reverse().find((t) => t.role === "you");
    const lastSi = [...turns].reverse().find((t) => t.role === "si");
    if (!lastYou || pending) return;
    setPending(true);
    setCoreErr(null);
    try {
      const res = await ask({
        data: {
          prompt: lastYou.text,
          context: `${lastSi?.text ?? ""}\nBoard ${pcb.title}. Lessons ${adapter.lessons}.`,
        },
      });
      if (res.ok) setCore(res.text);
      else setCoreErr(res.error);
    } catch {
      setCoreErr("Core model could not be reached. Local answer still stands.");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="flex h-dvh flex-col bg-bg text-fg">
      <header className="flex items-center justify-between gap-3 border-b border-line px-3 py-2 sm:px-4">
        <div className="flex items-center gap-3">
          <span className="grid h-9 w-9 place-items-center rounded-md bg-copper font-mono text-xs font-medium text-copper-ink">
            SI
          </span>
          <div>
            <p className="text-sm font-semibold tracking-tight">SI-LLM</p>
            <p className="hidden text-xs text-muted sm:block">
              Super intelligence · PCB, CAD, CAM, print, simulation
            </p>
          </div>
        </div>
        <p className="font-mono text-xs text-muted">
          {ready ? `adapter ${adapter.lessons}` : "…"} · local
        </p>
      </header>

      <div className="flex min-h-0 flex-1 flex-col md:flex-row">
        <nav className="flex gap-1 overflow-x-auto border-b border-line p-2 md:w-44 md:flex-col md:overflow-y-auto md:border-r md:border-b-0">
          {NAV.map((item) => {
            const Icon = item.icon;
            const on = desk === item.id;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => setDesk(item.id)}
                className={
                  "flex h-11 shrink-0 items-center gap-2 rounded-md px-3 text-sm " +
                  (on ? "bg-copper text-copper-ink" : "text-muted hover:bg-raised hover:text-fg")
                }
              >
                <Icon className="size-4" strokeWidth={1.75} />
                {item.label}
              </button>
            );
          })}
        </nav>

        <main className="min-h-0 flex-1 overflow-y-auto p-3 sm:p-4">
          {desk === "brief" && <BriefView />}
          {desk === "pcb" && <PcbView />}
          {desk === "cad" && <CadView />}
          {desk === "cam" && <CamView />}
          {desk === "print" && <PrintView />}
          {desk === "sim" && <SimView />}
          {desk === "train" && <TrainView />}
          {desk === "analyze" && <AnalyzeView />}
        </main>

        <aside
          className={
            "flex min-h-0 flex-col border-line md:w-80 md:border-l " +
            (logOpen ? "max-h-64 border-t md:max-h-none" : "hidden md:flex")
          }
        >
          <div ref={logRef} className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto p-3">
            {turns.map((t) => (
              <article key={t.id} className={t.role === "you" ? "self-end" : "self-start"}>
                <p className="mb-1 font-mono text-xs text-faint">
                  {t.role === "you" ? "You" : "SI-LLM"} · {t.modality}
                </p>
                <p
                  className={
                    "max-w-full rounded-lg px-3 py-2 text-sm " +
                    (t.role === "you" ? "bg-raised" : "border border-line bg-bg")
                  }
                >
                  {t.text}
                </p>
                {t.role === "si" && t.id !== "welcome" && (
                  <div className="mt-1 flex gap-1">
                    {[1, 2, 3, 4, 5].map((n) => (
                      <button
                        key={n}
                        type="button"
                        aria-label={`Score ${n}`}
                        onClick={() => rate(t.id, n)}
                        className={
                          "h-8 w-8 rounded-md text-xs " +
                          ((t.stars ?? 0) >= n ? "bg-copper text-copper-ink" : "text-faint")
                        }
                      >
                        {n}
                      </button>
                    ))}
                  </div>
                )}
              </article>
            ))}
            {core && (
              <article>
                <p className="mb-1 font-mono text-xs text-copper">Core model</p>
                <p className="rounded-lg border border-copper px-3 py-2 text-sm">{core}</p>
              </article>
            )}
            {coreErr && <p className="text-xs text-muted">{coreErr}</p>}
          </div>
        </aside>
      </div>

      <footer className="border-t border-line p-3 sm:p-4">
        {vision && modality === "vision" && (
          <VisionStrip vision={vision} onLabel={relabel} />
        )}
        {voiceNote && <p className="mb-2 text-xs text-muted">{voiceNote}</p>}
        <div className="mb-2 flex flex-wrap items-center gap-1">
          {(
            [
              ["text", "Text", Type],
              ["voice", "Voice", Mic],
              ["vision", "Vision", Eye],
            ] as const
          ).map(([id, label, Icon]) => (
            <button
              key={id}
              type="button"
              onClick={() => setModality(id)}
              className={
                "flex h-10 items-center gap-1 rounded-md border px-3 text-xs " +
                (modality === id ? "border-copper text-copper" : "border-line text-muted")
              }
            >
              <Icon className="size-3.5" />
              {label}
            </button>
          ))}
          <button
            type="button"
            onClick={() => setLogOpen((v) => !v)}
            className="h-10 rounded-md border border-line px-3 text-xs text-muted md:hidden"
          >
            {logOpen ? "Hide log" : "Log"}
          </button>
          <button
            type="button"
            onClick={() => void deepenLast()}
            disabled={pending}
            className="h-10 rounded-md border border-line px-3 text-xs text-muted disabled:opacity-40"
          >
            {pending ? "Asking core…" : "Deepen with core"}
          </button>
        </div>
        <form
          className="flex items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            submit();
          }}
        >
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            rows={2}
            placeholder={
              modality === "vision"
                ? "What should I look for in the image?"
                : modality === "voice"
                  ? "Hold the mic, or type if speech is unavailable"
                  : "Design a 4-layer motor driver, or ask about the bracket stress…"
            }
            className="min-h-11 flex-1 resize-none rounded-md border border-line bg-surface px-3 py-2 text-sm outline-none focus:border-copper"
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit();
              }
            }}
          />
          {modality === "voice" && (
            <button
              type="button"
              onClick={listen}
              className={
                "h-11 rounded-md px-3 text-sm font-medium " +
                (listening ? "bg-copper text-copper-ink" : "border border-line")
              }
            >
              {listening ? "Listening" : "Mic"}
            </button>
          )}
          {modality === "vision" && (
            <>
              <input
                ref={fileRef}
                type="file"
                accept="image/*"
                className="hidden"
                onChange={(e) => void onFile(e.target.files?.[0])}
              />
              <button
                type="button"
                onClick={() => fileRef.current?.click()}
                className="h-11 rounded-md border border-line px-3 text-sm"
              >
                Image
              </button>
            </>
          )}
          <button type="submit" className="h-11 rounded-md bg-copper px-4 text-sm font-medium text-copper-ink">
            Send
          </button>
        </form>
      </footer>
    </div>
  );
}

function VisionStrip({
  vision,
  onLabel,
}: {
  vision: VisionRead;
  onLabel: (d: Domain) => void;
}) {
  return (
    <div className="mb-2 flex flex-col gap-2 rounded-md border border-line bg-surface p-3 sm:flex-row sm:items-center">
      <div className="min-w-0 flex-1">
        <p className="font-mono text-xs text-copper">{vision.name}</p>
        <p className="text-xs text-muted">{vision.note}</p>
      </div>
      <div className="flex flex-wrap gap-1">
        {(["pcb", "cad", "cam", "print", "sim"] as Domain[]).map((d) => (
          <button
            key={d}
            type="button"
            onClick={() => onLabel(d)}
            className={
              "h-9 rounded-md border px-2 text-xs uppercase " +
              (vision.label === d ? "border-copper text-copper" : "border-line text-muted")
            }
          >
            {d}
          </button>
        ))}
      </div>
    </div>
  );
}
