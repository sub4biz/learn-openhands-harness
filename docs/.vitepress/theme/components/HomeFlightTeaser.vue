<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";

type Phase = {
  id: string;
  index: string;
  label: string;
  headline: string;
  on: string[];
  focus: string;
  feed: { t: string; kind: string; text: string }[];
  gauges: { e: number; d: number; c: number; v: number };
};

const phases: Phase[] = [
  {
    id: "model",
    index: "01",
    label: "Bare Model",
    headline: "Prompt in, text out.",
    on: ["task", "model", "answer", "w-task-model", "w-model-answer"],
    focus: "model",
    feed: [
      { t: "00:00", kind: "user", text: "why is test_users.py failing?" },
      { t: "00:01", kind: "model", text: "likely a fixture issue (unverified)" },
    ],
    gauges: { e: 5, d: 0, c: 0, v: 0 },
  },
  {
    id: "react",
    index: "02",
    label: "ReAct Loop",
    headline: "Reason, act, observe, repeat.",
    on: ["task", "model", "answer", "loop", "w-task-model", "w-model-answer"],
    focus: "loop",
    feed: [
      { t: "00:03", kind: "model", text: "plan · inspect failing test" },
      { t: "00:04", kind: "model", text: "pick action · need a tool" },
    ],
    gauges: { e: 15, d: 0, c: 0, v: 0 },
  },
  {
    id: "tools",
    index: "03",
    label: "Tools",
    headline: "Guesses become checked observations.",
    on: ["task", "model", "answer", "loop", "tools", "w-task-model", "w-model-answer", "w-model-tools"],
    focus: "tools",
    feed: [
      { t: "00:07", kind: "tool", text: "rg \"FAIL\" tests/" },
      { t: "00:08", kind: "obs", text: "test_email_lowercase FAILED" },
      { t: "00:09", kind: "tool", text: "read tests/test_users.py" },
    ],
    gauges: { e: 55, d: 5, c: 0, v: 10 },
  },
  {
    id: "memory",
    index: "04",
    label: "Memory",
    headline: "Stop re-discovering the same facts.",
    on: ["task", "model", "answer", "loop", "tools", "memory", "w-task-model", "w-model-answer", "w-model-tools", "w-model-memory"],
    focus: "memory",
    feed: [
      { t: "00:12", kind: "mem", text: "AGENTS.md · python 3.11, pytest" },
      { t: "00:13", kind: "mem", text: "prior trace · casing mismatch x2" },
    ],
    gauges: { e: 60, d: 60, c: 0, v: 10 },
  },
  {
    id: "safety",
    index: "05",
    label: "Safety",
    headline: "Bounded blast radius before more autonomy.",
    on: ["task", "model", "answer", "loop", "tools", "memory", "safety", "w-task-model", "w-model-answer", "w-model-tools", "w-model-memory"],
    focus: "safety",
    feed: [
      { t: "00:16", kind: "safe", text: "sandbox=workspace · network=off" },
      { t: "00:17", kind: "safe", text: "deny · rm -rf · needs approval" },
    ],
    gauges: { e: 60, d: 60, c: 70, v: 10 },
  },
  {
    id: "critic",
    index: "06",
    label: "Critic",
    headline: "Verification is the finish line, not confidence.",
    on: ["task", "model", "answer", "loop", "tools", "memory", "safety", "critic", "w-task-model", "w-model-answer", "w-model-tools", "w-model-memory", "w-model-critic"],
    focus: "critic",
    feed: [
      { t: "00:22", kind: "tool", text: "pytest tests/ -q" },
      { t: "00:23", kind: "obs", text: "47 passed · 0 failed" },
      { t: "00:24", kind: "crit", text: "verdict · keep" },
    ],
    gauges: { e: 75, d: 60, c: 70, v: 80 },
  },
  {
    id: "routing",
    index: "07",
    label: "Routing",
    headline: "The harness picks the model.",
    on: ["task", "router", "model", "answer", "loop", "tools", "memory", "safety", "critic", "w-task-router", "w-router-model", "w-model-answer", "w-model-tools", "w-model-memory", "w-model-critic"],
    focus: "router",
    feed: [
      { t: "00:25", kind: "rt", text: "classify · bugfix · S" },
      { t: "00:26", kind: "rt", text: "select · haiku-4-5" },
      { t: "00:28", kind: "rt", text: "escalate · sonnet-4-6" },
    ],
    gauges: { e: 80, d: 70, c: 70, v: 85 },
  },
  {
    id: "evidence",
    index: "08",
    label: "Benchmark",
    headline: "Leaderboard rows are agent + model.",
    on: ["task", "router", "model", "answer", "loop", "tools", "memory", "safety", "critic", "w-task-router", "w-router-model", "w-model-answer", "w-model-tools", "w-model-memory", "w-model-critic"],
    focus: "benchmark",
    feed: [
      { t: "00:30", kind: "eval", text: "same Claude Opus 4.6 · two harnesses" },
      { t: "00:31", kind: "eval", text: "harness moved the row ~18 pts" },
    ],
    gauges: { e: 90, d: 80, c: 85, v: 95 },
  },
];

const active = ref(0);
const paused = ref(false);
let timer: ReturnType<typeof setInterval> | null = null;

const phase = computed(() => phases[active.value]);
const gaugeStyle = computed(() => ({
  "--g-e": `${phase.value.gauges.e}%`,
  "--g-d": `${phase.value.gauges.d}%`,
  "--g-c": `${phase.value.gauges.c}%`,
  "--g-v": `${phase.value.gauges.v}%`,
}));

function partClass(id: string) {
  return { on: phase.value.on.includes(id), focus: phase.value.focus === id };
}

function jumpTo(i: number) {
  active.value = i;
}

function startTimer() {
  if (timer) return;
  timer = setInterval(() => {
    if (!paused.value) {
      active.value = (active.value + 1) % phases.length;
    }
  }, 3200);
}

function stopTimer() {
  if (timer) {
    clearInterval(timer);
    timer = null;
  }
}

onMounted(() => {
  const reduceMotion =
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (!reduceMotion) startTimer();
});

onBeforeUnmount(() => stopTimer());

// CTA href — VitePress base will resolve relative
const ctaHref = "/learn-openhands-harness/concepts/visual-intro";
</script>

<template>
  <section
    class="hft"
    @mouseenter="paused = true"
    @mouseleave="paused = false"
    aria-label="Visual intro preview"
  >
    <div class="hft-frame" :data-phase="phase.id">
      <!-- bar -->
      <div class="hft-bar">
        <div class="bar-left">
          <span class="dot" />
          <span class="bar-title">HARNESS CONSOLE · live preview</span>
        </div>
        <div class="bar-right">
          <span class="phase-tag">{{ phase.label }}</span>
          <span class="phase-num">{{ phase.index }}<span class="dim"> / 08</span></span>
        </div>
      </div>

      <!-- progress + tick rail (clickable) -->
      <div class="hft-rail">
        <div
          class="hft-rail-fill"
          :style="{ width: ((active + 1) / phases.length) * 100 + '%' }"
        />
        <button
          v-for="(p, i) in phases"
          :key="p.id"
          class="hft-tick"
          :class="{ active: i === active }"
          :aria-label="'Jump to phase ' + p.label"
          @click="jumpTo(i)"
        />
      </div>

      <!-- main: schematic + telemetry -->
      <div class="hft-main">
        <div class="hft-schem">
          <svg viewBox="0 0 520 280" class="hft-svg" role="img" aria-label="Agent system schematic">
            <defs>
              <pattern id="hft-grid" width="20" height="20" patternUnits="userSpaceOnUse">
                <path d="M 20 0 L 0 0 0 20" fill="none" stroke="rgb(249 240 217 / 7%)" stroke-width="1" />
              </pattern>
              <radialGradient id="hft-halo" cx="50%" cy="50%" r="50%">
                <stop offset="0%" stop-color="#ffff8b" stop-opacity="0.45" />
                <stop offset="100%" stop-color="#ffff8b" stop-opacity="0" />
              </radialGradient>
            </defs>
            <rect x="0" y="0" width="520" height="280" fill="url(#hft-grid)" />
            <line x1="260" y1="0" x2="260" y2="280" stroke="rgb(249 240 217 / 10%)" stroke-dasharray="2 4" />
            <line x1="0" y1="140" x2="520" y2="140" stroke="rgb(249 240 217 / 10%)" stroke-dasharray="2 4" />

            <!-- wires -->
            <g class="wires">
              <path class="wire" :class="partClass('w-task-model')" d="M 92 140 H 218" />
              <path class="wire" :class="partClass('w-model-answer')" d="M 302 140 H 428" />
              <path class="wire" :class="partClass('w-task-router')" d="M 70 122 V 38 H 230" />
              <path class="wire" :class="partClass('w-router-model')" d="M 260 60 V 110" />
              <path class="wire" :class="partClass('w-model-memory')" d="M 240 116 L 150 56" />
              <path class="wire" :class="partClass('w-model-critic')" d="M 282 116 L 380 56" />
              <path class="wire" :class="partClass('w-model-tools')" d="M 260 170 V 210" />
            </g>

            <!-- ReAct loop -->
            <g class="loop" :class="partClass('loop')">
              <circle cx="260" cy="140" r="48" fill="none" stroke="#ffff8b" stroke-opacity="0.35" stroke-dasharray="3 6" />
              <text x="260" y="92" class="loop-tag" text-anchor="middle">reason</text>
              <text x="316" y="146" class="loop-tag" text-anchor="start">act</text>
              <text x="260" y="200" class="loop-tag" text-anchor="middle">observe</text>
            </g>

            <!-- nodes -->
            <g class="node" :class="partClass('task')" transform="translate(12,110)">
              <rect width="80" height="60" rx="6" />
              <text x="40" y="24" text-anchor="middle" class="n-lbl">TASK</text>
              <text x="40" y="44" text-anchor="middle" class="n-sub">prompt</text>
            </g>
            <g class="node" :class="partClass('router')" transform="translate(210,8)">
              <rect width="100" height="60" rx="6" />
              <text x="50" y="24" text-anchor="middle" class="n-lbl">ROUTER</text>
              <text x="50" y="44" text-anchor="middle" class="n-sub">choose model</text>
            </g>
            <g class="node" :class="partClass('memory')" transform="translate(80,8)">
              <rect width="100" height="60" rx="6" />
              <text x="50" y="24" text-anchor="middle" class="n-lbl">MEMORY</text>
              <text x="50" y="44" text-anchor="middle" class="n-sub">artifacts</text>
            </g>
            <g class="node" :class="partClass('critic')" transform="translate(340,8)">
              <rect width="100" height="60" rx="6" />
              <text x="50" y="24" text-anchor="middle" class="n-lbl">CRITIC</text>
              <text x="50" y="44" text-anchor="middle" class="n-sub">verify</text>
            </g>
            <g class="node node-primary" :class="partClass('model')" transform="translate(218,110)">
              <circle cx="0" cy="0" r="42" class="halo" fill="url(#hft-halo)" />
              <rect width="84" height="60" rx="8" />
              <text x="42" y="24" text-anchor="middle" class="n-lbl">MODEL</text>
              <text x="42" y="44" text-anchor="middle" class="n-sub">reason</text>
            </g>
            <g class="node" :class="partClass('answer')" transform="translate(428,110)">
              <rect width="80" height="60" rx="6" />
              <text x="40" y="24" text-anchor="middle" class="n-lbl">RESULT</text>
              <text x="40" y="44" text-anchor="middle" class="n-sub">answer / diff</text>
            </g>
            <g class="node tools-group" :class="partClass('tools')" transform="translate(180,210)">
              <rect width="160" height="60" rx="6" />
              <text x="80" y="18" text-anchor="middle" class="n-lbl">TOOLS</text>
              <g class="tool-chips">
                <rect x="10" y="28" width="40" height="22" rx="3" />
                <text x="30" y="43" text-anchor="middle" class="n-chip">shell</text>
                <rect x="60" y="28" width="40" height="22" rx="3" />
                <text x="80" y="43" text-anchor="middle" class="n-chip">files</text>
                <rect x="110" y="28" width="40" height="22" rx="3" />
                <text x="130" y="43" text-anchor="middle" class="n-chip">test</text>
              </g>
            </g>
            <g class="safety-ring" :class="partClass('safety')" transform="translate(160,194)">
              <rect width="200" height="96" rx="14" fill="none" />
              <text x="100" y="-2" text-anchor="middle" class="n-lbl-ring">SAFETY · sandbox · policy · budget</text>
            </g>
          </svg>
        </div>

        <div class="hft-feed">
          <div class="feed-head">
            <span class="rec-dot" />
            <span>TELEMETRY</span>
          </div>
          <p class="feed-headline">{{ phase.headline }}</p>
          <ol :key="active">
            <li
              v-for="(line, i) in phase.feed"
              :key="line.t + i"
              :class="'feed-' + line.kind"
              :style="{ animationDelay: i * 90 + 'ms' }"
            >
              <span class="ts">{{ line.t }}</span>
              <span class="kind">{{ line.kind }}</span>
              <span class="msg">{{ line.text }}</span>
            </li>
          </ol>

          <transition name="hft-bench-fade">
            <div v-if="phase.id === 'evidence'" class="hft-bench">
              <div class="hft-bench-head">
                <span>TERMINAL-BENCH 2.0</span>
                <strong>same model · two harnesses</strong>
              </div>
              <div class="hft-bench-row">
                <span class="hft-bench-name">Meta-Harness</span>
                <span class="hft-bench-model">Opus 4.6</span>
                <span class="hft-bench-score hi">76.4%</span>
              </div>
              <div class="hft-bench-row">
                <span class="hft-bench-name">Claude Code</span>
                <span class="hft-bench-model">Opus 4.6</span>
                <span class="hft-bench-score lo">58.0%</span>
              </div>
              <p class="hft-bench-foot">~18 pts from harness alone · public leaderboard, June 2026</p>
            </div>
          </transition>
        </div>
      </div>

      <!-- mini gauges -->
      <div class="hft-gauges" :style="gaugeStyle">
        <div class="g"><span>EVIDENCE</span><i class="bar"><i class="fill" data-key="e" /></i></div>
        <div class="g"><span>DURABILITY</span><i class="bar"><i class="fill" data-key="d" /></i></div>
        <div class="g"><span>CONTAINMENT</span><i class="bar"><i class="fill" data-key="c" /></i></div>
        <div class="g"><span>VERIFICATION</span><i class="bar"><i class="fill" data-key="v" /></i></div>
      </div>
    </div>

    <div class="hft-cta">
      <div class="cta-text">
        <p class="cta-eyebrow">The course in one visual</p>
        <p class="cta-line">
          One task. Eight versions of the agent around the same model.
          Scroll the harness into view.
        </p>
      </div>
      <a class="cta-btn" :href="ctaHref">
        Open the Visual Intro
        <span aria-hidden="true">→</span>
      </a>
    </div>
  </section>
</template>

<style scoped>
.hft {
  position: relative;
  margin: 12px 0 48px;
  width: 100%;
}

.hft-frame {
  position: relative;
  border: 1px solid #22150d;
  border-radius: 12px;
  background: #181009;
  background-image:
    radial-gradient(circle at 12% 0%, rgb(255 255 139 / 10%), transparent 40%),
    radial-gradient(circle at 88% 100%, rgb(227 23 0 / 8%), transparent 38%);
  box-shadow:
    0 22px 60px rgb(34 21 13 / 30%),
    inset 0 0 0 1px rgb(249 240 217 / 4%);
  color: #f9f0d9;
  overflow: hidden;
}

.hft-bar {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 16px;
  align-items: center;
  padding: 11px 16px;
  border-bottom: 1px solid rgb(249 240 217 / 12%);
  background: linear-gradient(180deg, rgb(255 255 139 / 6%), transparent);
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}
.bar-left { display: flex; gap: 8px; align-items: center; }
.bar-left .dot {
  display: inline-block;
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: #ff5942;
  box-shadow: 0 0 10px rgb(255 89 66 / 70%);
  animation: hft-pulse 1.6s ease-in-out infinite;
}
.bar-title { color: #f9f0d9; font-weight: 500; }
.bar-right { display: flex; gap: 10px; align-items: baseline; }
.phase-tag {
  border: 1px solid rgb(255 255 139 / 50%);
  border-radius: 999px;
  background: rgb(255 255 139 / 10%);
  color: #ffff8b;
  padding: 2px 9px;
  font-size: 10px;
}
.phase-num { color: #ffff8b; font-size: 14px; font-weight: 500; }
.phase-num .dim { color: rgb(249 240 217 / 45%); }

@keyframes hft-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

/* tick rail */
.hft-rail {
  position: relative;
  height: 18px;
  background: rgb(249 240 217 / 5%);
  border-bottom: 1px solid rgb(249 240 217 / 10%);
}
.hft-rail-fill {
  position: absolute;
  inset: 0 auto 0 0;
  background: linear-gradient(90deg, #ffff8b, #ffd400);
  opacity: 0.18;
  transition: width 380ms cubic-bezier(0.22, 0.65, 0.3, 1);
}
.hft-tick {
  position: relative;
  z-index: 1;
  flex: 1;
  width: calc(100% / 8);
  height: 100%;
  margin: 0;
  padding: 0;
  border: 0;
  background: transparent;
  cursor: pointer;
  float: left;
}
.hft-tick::before {
  content: "";
  display: block;
  width: 6px;
  height: 6px;
  margin: 6px auto;
  border-radius: 50%;
  background: rgb(249 240 217 / 30%);
  transition: background 220ms ease, transform 220ms ease;
}
.hft-tick:hover::before { background: rgb(255 255 139 / 70%); transform: scale(1.4); }
.hft-tick.active::before { background: #ffff8b; transform: scale(1.6); box-shadow: 0 0 10px rgb(255 255 139 / 70%); }

/* main */
.hft-main {
  display: grid;
  grid-template-columns: 1.1fr 0.9fr;
  min-height: 300px;
}

.hft-schem {
  padding: 14px 14px 6px;
  border-right: 1px solid rgb(249 240 217 / 10%);
  background:
    linear-gradient(rgb(249 240 217 / 3%) 1px, transparent 1px) 0 0 / 22px 22px,
    linear-gradient(90deg, rgb(249 240 217 / 3%) 1px, transparent 1px) 0 0 / 22px 22px,
    radial-gradient(circle at 50% 55%, #221710, #100a06);
}
.hft-svg {
  display: block;
  width: 100%;
  height: auto;
  max-height: 280px;
}

/* node styles (mirror full console) */
.node rect {
  fill: rgb(249 240 217 / 4%);
  stroke: rgb(249 240 217 / 22%);
  stroke-width: 1;
  transition: fill 320ms ease, stroke 320ms ease;
}
.node text {
  font-family: var(--vp-font-family-mono);
  font-size: 10px;
  letter-spacing: 0.04em;
  fill: rgb(249 240 217 / 40%);
  text-transform: uppercase;
  transition: fill 320ms ease;
}
.node .n-lbl { font-size: 11px; fill: rgb(249 240 217 / 55%); font-weight: 500; }
.node .n-sub { font-size: 9.5px; letter-spacing: 0.05em; }
.node .n-chip { font-size: 9px; fill: rgb(249 240 217 / 55%); }
.node { opacity: 0.28; transition: opacity 320ms ease, transform 320ms ease; }
.node.on { opacity: 1; }
.node.on rect { fill: rgb(255 255 139 / 8%); stroke: rgb(255 255 139 / 55%); }
.node.on text { fill: #f9f0d9; }
.node.on .n-lbl { fill: #ffff8b; }
.node.focus rect { fill: rgb(255 255 139 / 18%); stroke: #ffff8b; }
.node-primary.on rect { fill: rgb(255 255 139 / 14%); stroke: #ffff8b; }
.node-primary .halo { opacity: 0; transition: opacity 320ms ease; }
.node-primary.on .halo { opacity: 0.9; }
.tools-group .tool-chips rect { fill: rgb(255 255 139 / 6%); stroke: rgb(255 255 139 / 30%); }
.tools-group.on .tool-chips rect { fill: rgb(255 255 139 / 14%); stroke: #ffff8b; }

.safety-ring rect { stroke-dasharray: 5 6; stroke: transparent; transition: stroke 320ms ease; }
.safety-ring .n-lbl-ring {
  font-family: var(--vp-font-family-mono);
  font-size: 9.5px;
  letter-spacing: 0.08em;
  fill: transparent;
  text-transform: uppercase;
  transition: fill 320ms ease;
}
.safety-ring.on rect { stroke: rgb(255 92 70 / 75%); }
.safety-ring.on .n-lbl-ring { fill: rgb(255 121 96 / 95%); }

.wire {
  fill: none;
  stroke: rgb(249 240 217 / 12%);
  stroke-width: 1.4;
  stroke-dasharray: 4 5;
  transition: stroke 320ms ease, stroke-opacity 320ms ease;
}
.wire.on {
  stroke: #ffff8b;
  stroke-opacity: 0.7;
  animation: hft-flow 1.6s linear infinite;
}
@keyframes hft-flow { to { stroke-dashoffset: -18; } }

.loop { opacity: 0; transition: opacity 320ms ease; }
.loop.on { opacity: 1; }
.loop .loop-tag {
  font-family: var(--vp-font-family-mono);
  font-size: 9px;
  letter-spacing: 0.08em;
  fill: rgb(255 255 139 / 75%);
  text-transform: uppercase;
}

/* feed */
.hft-feed {
  display: flex;
  flex-direction: column;
  padding: 14px 16px;
  background:
    repeating-linear-gradient(to bottom, rgb(249 240 217 / 2%) 0 1px, transparent 1px 4px),
    #120c08;
}
.feed-head {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 8px;
  color: rgb(249 240 217 / 70%);
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}
.rec-dot {
  display: inline-block;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #ffff8b;
  box-shadow: 0 0 8px rgb(255 255 139 / 80%);
}
.feed-headline {
  margin: 0 0 10px;
  color: #ffff8b;
  font-family: "Quincy CF", var(--vp-font-family-base);
  font-size: 19px;
  font-weight: 400;
  line-height: 1.2;
}
.hft-feed ol {
  display: grid;
  gap: 6px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.hft-feed li {
  display: grid;
  gap: 8px;
  grid-template-columns: 44px 38px 1fr;
  align-items: baseline;
  padding: 6px 8px;
  border: 1px solid rgb(249 240 217 / 8%);
  border-left: 2px solid rgb(255 255 139 / 35%);
  border-radius: 4px;
  background: rgb(249 240 217 / 3%);
  color: #f9f0d9;
  font-family: var(--vp-font-family-mono);
  font-size: 11.5px;
  line-height: 1.35;
  opacity: 0;
  animation: hft-feed-in 320ms ease forwards;
}
.hft-feed li .ts { color: rgb(249 240 217 / 45%); }
.hft-feed li .kind { color: rgb(255 255 139 / 80%); font-weight: 500; text-transform: lowercase; }
.hft-feed li .msg { color: rgb(249 240 217 / 90%); word-break: break-word; }
@keyframes hft-feed-in {
  from { opacity: 0; transform: translateY(4px); }
  to { opacity: 1; transform: translateY(0); }
}
.feed-user { border-left-color: rgb(255 255 139 / 70%) !important; }
.feed-model { border-left-color: rgb(122 199 255 / 80%) !important; }
.feed-model .kind { color: #92cbff; }
.feed-tool { border-left-color: rgb(95 207 153 / 80%) !important; }
.feed-tool .kind { color: #6cd9a3; }
.feed-obs { border-left-color: rgb(178 178 178 / 70%) !important; }
.feed-obs .kind { color: #cfc8b7; }
.feed-mem { border-left-color: rgb(160 226 122 / 80%) !important; }
.feed-mem .kind { color: #a5e07d; }
.feed-safe { border-left-color: rgb(255 121 96 / 90%) !important; }
.feed-safe .kind { color: #ff8e76; }
.feed-crit { border-left-color: rgb(255 195 120 / 90%) !important; }
.feed-crit .kind { color: #ffc378; }
.feed-rt { border-left-color: rgb(214 156 255 / 85%) !important; }
.feed-rt .kind { color: #d49cff; }
.feed-eval { border-left-color: #ffff8b !important; background: rgb(255 255 139 / 6%); }
.feed-eval .kind { color: #ffff8b; }

/* mini benchmark card at phase 8 */
.hft-bench {
  margin-top: 10px;
  border: 1px solid rgb(255 255 139 / 45%);
  border-radius: 6px;
  background: rgb(255 255 139 / 6%);
  padding: 10px 12px;
}
.hft-bench-head {
  display: flex;
  justify-content: space-between;
  margin-bottom: 8px;
  color: #ffff8b;
  font-family: var(--vp-font-family-mono);
  font-size: 10px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}
.hft-bench-head strong {
  color: #f9f0d9;
  font-weight: 500;
}
.hft-bench-row {
  display: grid;
  grid-template-columns: 1fr auto auto;
  gap: 10px;
  align-items: baseline;
  padding: 5px 0;
  border-bottom: 1px solid rgb(249 240 217 / 10%);
  color: #f9f0d9;
  font-family: var(--vp-font-family-mono);
  font-size: 11.5px;
}
.hft-bench-row:last-of-type {
  border-bottom: 0;
}
.hft-bench-name {
  font-weight: 500;
}
.hft-bench-model {
  color: #ff8e76;
  font-size: 10.5px;
}
.hft-bench-score {
  font-weight: 500;
  font-size: 13px;
}
.hft-bench-score.hi { color: #ffff8b; }
.hft-bench-score.lo { color: rgb(249 240 217 / 70%); }
.hft-bench-foot {
  margin: 8px 0 0;
  color: rgb(249 240 217 / 55%);
  font-family: var(--vp-font-family-mono);
  font-size: 10px;
  letter-spacing: 0.04em;
  line-height: 1.4;
}

.hft-bench-fade-enter-active {
  transition: opacity 240ms ease, transform 240ms ease;
}
.hft-bench-fade-enter-from {
  opacity: 0;
  transform: translateY(6px);
}

/* gauges */
.hft-gauges {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  border-top: 1px solid rgb(249 240 217 / 10%);
}
.hft-gauges .g {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px 14px;
  border-right: 1px solid rgb(249 240 217 / 8%);
  color: rgb(249 240 217 / 70%);
  font-family: var(--vp-font-family-mono);
  font-size: 10px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.hft-gauges .g:last-child { border-right: 0; }
.hft-gauges .bar {
  display: block;
  height: 4px;
  border-radius: 999px;
  background: rgb(249 240 217 / 8%);
  overflow: hidden;
}
.hft-gauges .fill {
  display: block;
  height: 100%;
  background: linear-gradient(90deg, #ffff8b, #ffd400);
  transition: width 460ms cubic-bezier(0.22, 0.65, 0.3, 1);
  width: 0;
}
.hft-gauges .fill[data-key="e"] { width: var(--g-e, 0%); }
.hft-gauges .fill[data-key="d"] { width: var(--g-d, 0%); }
.hft-gauges .fill[data-key="c"] {
  width: var(--g-c, 0%);
  background: linear-gradient(90deg, #ff8e76, #ffb169);
}
.hft-gauges .fill[data-key="v"] {
  width: var(--g-v, 0%);
  background: linear-gradient(90deg, #a5e07d, #ffe165);
}

/* CTA strip */
.hft-cta {
  display: flex;
  gap: 18px;
  align-items: center;
  justify-content: space-between;
  margin-top: 14px;
  padding: 14px 18px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 10px;
  background: var(--vp-c-bg-soft);
}
.cta-text { flex: 1 1 0; min-width: 0; }
.cta-eyebrow {
  margin: 0;
  color: var(--oh-brown);
  font-family: var(--vp-font-family-mono);
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.cta-line {
  margin: 4px 0 0;
  color: var(--vp-c-text-1);
  font-family: "Quincy CF", var(--vp-font-family-base);
  font-size: 19px;
  line-height: 1.25;
}
.cta-btn {
  display: inline-flex;
  gap: 10px;
  align-items: center;
  flex-shrink: 0;
  border: 1px solid var(--oh-fg);
  border-radius: 8px;
  background: var(--oh-fg);
  color: var(--oh-bg);
  padding: 12px 18px;
  font-family: var(--vp-font-family-base);
  font-size: 14px;
  font-weight: 500;
  text-decoration: none;
  transition: background 200ms ease, color 200ms ease, transform 200ms ease;
}
.cta-btn:hover {
  background: var(--oh-brown);
  border-color: var(--oh-brown);
  transform: translateY(-1px);
}

/* responsive */
@media (max-width: 920px) {
  .hft-main {
    grid-template-columns: 1fr;
  }
  .hft-schem {
    border-right: 0;
    border-bottom: 1px solid rgb(249 240 217 / 10%);
  }
  .hft-gauges {
    grid-template-columns: repeat(2, 1fr);
  }
  .hft-gauges .g:nth-child(2n) { border-right: 0; }
  .hft-gauges .g:nth-child(-n+2) { border-bottom: 1px solid rgb(249 240 217 / 8%); }
  .hft-cta {
    flex-direction: column;
    align-items: flex-start;
  }
  .cta-btn { width: 100%; justify-content: center; }
}

@media (max-width: 560px) {
  .hft-bar { grid-template-columns: 1fr auto; }
  .bar-title { font-size: 10px; }
  .hft-feed li { grid-template-columns: 40px 32px 1fr; font-size: 10.5px; }
  .feed-headline { font-size: 16px; }
}

:global(.dark) .hft-cta {
  background: rgb(241 234 224 / 4%);
  border-color: rgb(249 240 217 / 14%);
}
:global(.dark) .cta-line { color: #f9f0d9; }
:global(.dark) .cta-btn {
  background: #ffe165;
  border-color: #ffe165;
  color: #22150d;
}
:global(.dark) .cta-btn:hover {
  background: #ffff8b;
  border-color: #ffff8b;
}

@media (prefers-reduced-motion: reduce) {
  .wire.on,
  .bar-left .dot {
    animation: none !important;
  }
  .hft-feed li {
    animation: none !important;
    opacity: 1;
  }
  .hft-rail-fill,
  .hft-gauges .fill,
  .node,
  .wire {
    transition: none !important;
  }
}
</style>
