import type { ReactNode } from "react";
import s from "./book.module.css";

type Kind = "step" | "ask" | "person" | "good" | "store";

// One labelled box; a second line is the quieter detail under the name.
function Box({ x, y, w, h = 40, kind = "step", title, sub }: {
  x: number; y: number; w: number; h?: number; kind?: Kind; title: string; sub?: string;
}) {
  const cx = x + w / 2;
  const cy = y + h / 2;
  return (
    <g className={s[kind]}>
      <rect x={x} y={y} width={w} height={h} rx={kind === "store" ? 14 : 7} />
      <text x={cx} y={sub ? cy - 3 : cy + 5} textAnchor="middle" className={s.dTitle}>
        {title}
      </text>
      {sub && (
        <text x={cx} y={cy + 14} textAnchor="middle" className={s.dSub}>
          {sub}
        </text>
      )}
    </g>
  );
}

function Arrow({ d, label, lx, ly, loop = false }: { d: string; label?: string; lx?: number; ly?: number; loop?: boolean }) {
  return (
    <>
      <path d={d} className={loop ? s.loop : s.wire} markerEnd={loop ? "url(#tip-loop)" : "url(#tip)"} />
      {label && (
        <text x={lx} y={ly} className={s.dSub}>
          {label}
        </text>
      )}
    </>
  );
}

function Figure({ label, caption, viewBox, children }: { label: string; caption: string; viewBox: string; children: ReactNode }) {
  return (
    <figure className={s.figure}>
      <svg viewBox={viewBox} role="img" aria-label={label}>
        <defs>
          <marker id="tip" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M0 0 L10 5 L0 10 z" className={s.tip} />
          </marker>
          <marker id="tip-loop" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M0 0 L10 5 L0 10 z" className={s.tipLoop} />
          </marker>
        </defs>
        {children}
      </svg>
      <figcaption>{caption}</figcaption>
    </figure>
  );
}

export function JourneyDiagram() {
  return (
    <Figure
      viewBox="0 0 640 690"
      label="A post's path: a reader sends a link; a repeat is answered at once; otherwise Hamsa downloads it, reads the post, matches the footage, gathers evidence, drafts a verdict, and fixed rules sort it for a checker, who publishes; the reader is told and the footage is remembered, so the next copy is matched."
      caption="One post through Hamsa. The dashed line is the memory: what a checker publishes is matched the next time it appears."
    >
      <Box x={200} y={16} w={240} title="A reader sends a link" />
      <Arrow d="M320 56 V84" />
      <Box x={170} y={86} w={300} kind="ask" title="Seen this link, post or file before?" />
      <Arrow d="M470 106 H500" label="yes" lx={474} ly={98} />
      <Box x={502} y={86} w={128} kind="good" title="Answer at once" />
      <Arrow d="M320 126 V154" label="no" lx={328} ly={145} />
      <Box x={200} y={156} w={240} title="Download, take keyframes" />
      <Arrow d="M290 196 L180 234" />
      <Arrow d="M350 196 L460 234" />
      <Box x={40} y={236} w={260} h={50} title="Read the post" sub="the claim, places, numbers" />
      <Box x={340} y={236} w={260} h={50} title="Match the footage" sub="against footage of known origin" />
      <Arrow d="M170 286 V314" />
      <Box x={40} y={316} w={260} h={50} title="Gather evidence" sub="news, fact-checks, the web" />
      <Arrow d="M170 366 L270 394" />
      <Arrow d="M470 286 V421 H442" />
      <Box x={200} y={396} w={240} h={50} title="Draft the verdict" sub="English and Nepali, with sources" />
      <Arrow d="M320 446 V474" />
      <Box x={200} y={476} w={240} title="Fixed rules sort the case" />
      <Arrow d="M320 516 V544" />
      <Box x={170} y={546} w={300} kind="person" title="A checker decides and publishes" />
      <Arrow d="M280 586 L190 624" />
      <Arrow d="M360 586 L450 624" />
      <Box x={40} y={626} w={260} kind="good" title="The reader is told" />
      <Box x={340} y={626} w={260} kind="good" title="The footage is remembered" />
      <Arrow d="M600 646 H624 V261 H602" loop />
    </Figure>
  );
}

export function FingerprintDiagram() {
  const bits = [
    [0, 0], [32, 0], [96, 0], [48, 16], [112, 16], [16, 32], [80, 32], [0, 48],
    [64, 48], [32, 64], [96, 64], [16, 80], [48, 96], [112, 96], [0, 112], [80, 112],
  ];
  const bars = [60, 30, 80, 45, 15, 70, 40, 90, 25, 55, 35, 75];
  const left = [[18, 30], [55, 22], [40, 60], [65, 85], [20, 92]];
  const right = [[122, 34], [148, 28], [138, 56], [155, 73], [124, 78]];
  return (
    <Figure
      viewBox="0 0 640 230"
      label="Three fingerprints of one frame: a 64-bit perceptual hash, an image embedding of numbers, and keypoints matched between two frames"
      caption="One keyframe, three fingerprints. Each catches what the others miss, and none needs the video itself."
    >
      <text className={s.dTitle} x={20} y={28}>Perceptual hash: 64 bits</text>
      <g transform="translate(20,40)">
        <rect width={128} height={128} className={s.panel} />
        {bits.map(([x, y]) => (
          <rect key={`${x}-${y}`} x={x} y={y} width={16} height={16} className={s.ink} />
        ))}
      </g>
      <text className={s.dSub} x={20} y={190}>re-encodes, resizes,</text>
      <text className={s.dSub} x={20} y={206}>light crops</text>

      <text className={s.dTitle} x={225} y={28}>Embedding: 768 numbers</text>
      <g transform="translate(225,48)">
        {bars.map((h, i) => (
          <rect key={i} x={i * 12} y={100 - h} width={9} height={h} className={s.glacier} />
        ))}
        <rect x={0} y={100} width={141} height={1.5} className={s.rule} />
      </g>
      <text className={s.dSub} x={225} y={190}>the same scene under captions,</text>
      <text className={s.dSub} x={225} y={206}>overlays and heavier edits</text>

      <text className={s.dTitle} x={430} y={28}>Keypoints that line up</text>
      <g transform="translate(430,40)">
        <rect width={80} height={110} className={s.panel} />
        <rect x={110} y={15} width={80} height={80} className={s.panel} />
        {left.map(([x1, y1], i) => (
          <line key={i} x1={x1} y1={y1} x2={right[i][0]} y2={right[i][1]} className={s.match} />
        ))}
        {[...left, ...right].map(([cx, cy]) => (
          <circle key={`${cx}-${cy}`} cx={cx} cy={cy} r={3.5} className={s.point} />
        ))}
      </g>
      <text className={s.dSub} x={430} y={190}>proves the same shot inside</text>
      <text className={s.dSub} x={430} y={206}>crops, bars and screenshots</text>
    </Figure>
  );
}

export function RulesDiagram() {
  const q = 40;
  const out = 400;
  return (
    <Figure
      viewBox="0 0 640 470"
      label="The sorting rules in order: a failed step goes to a checker; a repeat is merged; a post with no checkable claim is dismissed; conflicting evidence goes to a checker; an unfakeable signal makes it a quick check; anything else goes to a checker with the reason."
      caption="The rules run in this order, every time. The AI supplies the answers to each question; the rules, written down and tested, decide."
    >
      <Box x={q} y={20} w={300} kind="ask" title="Did any step fail?" />
      <Arrow d="M340 40 H398" label="yes" lx={354} ly={32} />
      <Box x={out} y={20} w={220} kind="person" title="A checker looks" />
      <Arrow d="M190 60 V88" label="no" lx={198} ly={79} />
      <Box x={q} y={90} w={300} kind="ask" title="Seen this post before?" />
      <Arrow d="M340 110 H398" label="yes" lx={354} ly={102} />
      <Box x={out} y={90} w={220} title="Merged with the earlier report" />
      <Arrow d="M190 130 V158" label="no" lx={198} ly={149} />
      <Box x={q} y={160} w={300} kind="ask" title="Is there a claim to check?" />
      <Arrow d="M340 180 H398" label="no" lx={356} ly={172} />
      <Box x={out} y={160} w={220} title="Dismissed" />
      <Arrow d="M190 200 V228" label="yes" lx={198} ly={219} />
      <Box x={q} y={230} w={300} kind="ask" title="Does the evidence conflict?" />
      <Arrow d="M340 250 H398" label="yes" lx={354} ly={242} />
      <Box x={out} y={230} w={220} h={40} kind="person" title="A checker, shown the conflict" />
      <Arrow d="M190 270 V298" label="no" lx={198} ly={289} />
      <Box x={q} y={300} w={300} h={64} kind="ask" title="Is there a signal that can't be faked?" sub="old footage + false, an AI watermark, a fact-check…" />
      <Arrow d="M340 332 H398" label="yes" lx={354} ly={324} />
      <Box x={out} y={306} w={220} h={52} kind="good" title="Quick check" sub="one click from publishing" />
      <Arrow d="M190 364 V402" label="no" lx={198} ly={388} />
      <Box x={q} y={404} w={300} kind="person" title="A checker, told why it fell short" />
    </Figure>
  );
}

export function SystemDiagram() {
  const doors: [string, number][] = [["Website", 40], ["Telegram bot", 100], ["Messenger bot", 160], ["Checker desk", 220]];
  const tools: [string, string, number, Kind][] = [
    ["Vision model", "Qwen3-VL-8B, on the GPU", 20, "step"],
    ["Search and match", "bge-m3, SigLIP, ORB, on the CPU", 80, "step"],
    ["Vector store", "Qdrant: archive and news", 140, "store"],
    ["Web search", "SearXNG, self-hosted", 200, "step"],
    ["Verdict model", "gpt-oss on Groq, optional", 260, "step"],
  ];
  return (
    <Figure
      viewBox="0 0 640 390"
      label="What runs where: the website, bots and desk write to the API and the case store; one worker takes each case and calls the vision model, search and matching, the vector store, web search and the verdict model; a news watcher keeps the vector store current."
      caption="Everything runs on one laptop with an 8 GB graphics card, started with one command. The verdict model on Groq is optional: without it, the vision model drafts and every case goes to a checker."
    >
      {doors.map(([name, y]) => (
        <Box key={name} x={20} y={y} w={150} title={name} />
      ))}
      <Box x={230} y={40} w={160} title="API" />
      <Box x={230} y={140} w={160} h={44} kind="store" title="Case store" sub="SQLite: cases and jobs" />
      <Box x={230} y={250} w={160} h={44} kind="person" title="Worker" sub="one case at a time" />
      <Box x={230} y={330} w={160} title="News watcher" />
      <Arrow d="M170 60 H228" />
      <Arrow d="M170 240 L228 70" />
      <Arrow d="M170 120 L228 152" />
      <Arrow d="M170 180 L228 168" />
      <Arrow d="M310 80 V138" />
      <Arrow d="M310 248 V186" />
      <path d="M390 272 H420 V43 M420 283 V272" className={s.wire} />
      {tools.map(([name, sub, y, kind]) => (
        <g key={name}>
          <Arrow d={`M420 ${y + 23} H448`} />
          <Box x={450} y={y} w={175} h={46} kind={kind} title={name} sub={sub} />
        </g>
      ))}
      <Arrow d="M390 342 L460 188" />
    </Figure>
  );
}
