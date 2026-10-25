import type { ReactNode } from "react";
import { FingerprintDiagram, JourneyDiagram, RulesDiagram, SystemDiagram } from "./diagrams";
import s from "./book.module.css";

export const REPO = "https://github.com/masabinhok/hamsa";

export type Chapter = { slug: string; part: string; title: string; lede: string; body: ReactNode };

// The boxes the book teaches with: a term from zero, the one line to remember, a measured number,
// and the questions people ask.
function Zero({ term, children }: { term: string; children: ReactNode }) {
  return (
    <aside className={`${s.block} ${s.zero}`}>
      <span className={s.tag}>From zero: {term}</span>
      {children}
    </aside>
  );
}

function Line({ children }: { children: ReactNode }) {
  return (
    <aside className={`${s.block} ${s.line}`}>
      <span className={s.tag}>In one line</span>
      <p>{children}</p>
    </aside>
  );
}

function Num({ big, children }: { big: string; children: ReactNode }) {
  return (
    <aside className={`${s.block} ${s.num}`}>
      <span className={s.tag}>The number</span>
      <span className={s.big}>{big}</span>
      <p>{children}</p>
    </aside>
  );
}

function Asks({ items }: { items: [string, ReactNode][] }) {
  return (
    <aside className={`${s.block} ${s.asks}`}>
      <span className={s.tag}>You might ask</span>
      <dl>
        {items.map(([question, answer]) => (
          <div key={question}>
            <dt>{question}</dt>
            <dd>{answer}</dd>
          </div>
        ))}
      </dl>
    </aside>
  );
}

const STORY = "The story";
const HOW = "How it works";
const PROOF = "The proof";

export const chapters: Chapter[] = [
  {
    slug: "the-flood",
    part: STORY,
    title: "The flood, and the videos that came after",
    lede: "Why a fact-check desk in Nepal needed help, and the two observations Hamsa is built on.",
    body: (
      <>
        <p className={s.story}>
          Early on the morning of 26 August 2026, a wall of water came down the Bhotekoshi river in Rasuwa. Ice and rock
          had collapsed high up near the Tibetan border, and the flood swept through villages, hydropower camps, roads
          and homes. Within days the official count passed 900 dead, with thousands missing.
        </p>
        <p className={s.story}>
          Within hours, social media filled with flood videos. Many were real. Many were not. A 2025 flash flood in
          India&apos;s Uttarakhand went round as &quot;Bhotekoshi today&quot;. A glacier collapse filmed in Alaska became
          &quot;the moment the glacier burst in Rasuwa&quot;. AI-made videos showed bridges folding into rivers and
          elephants carrying children to safety.
        </p>
        <p className={s.story}>
          Sorting this out is the work of fact-checkers: Nepal Factcheck, Newschecker Nepal, TechPana, and abroad AFP,
          BOOM, Alt News and others. The Nepal Press Council&apos;s reporting portal received 101 complaints within days.
          Each one was traced by hand.
        </p>
        <h3>What &quot;by hand&quot; means</h3>
        <p>Watch a fact-checker work on one viral flood video and the same five steps come up every time:</p>
        <ol>
          <li>
            <strong>Work out the claim.</strong> The caption says &quot;Bhotekoshi today&quot;, the on-screen text says
            &quot;1,000+ missing&quot;. Which of those is being claimed?
          </li>
          <li>
            <strong>Check whether the footage has appeared before.</strong> Screenshot a few frames, paste them into a
            reverse image search, scroll through the results.
          </li>
          <li>
            <strong>Search for evidence:</strong> news from the right dates, official figures, fact-checks published
            elsewhere, often in another language.
          </li>
          <li>
            <strong>Write the verdict,</strong> in Nepali for the public and often in English too.
          </li>
          <li>
            <strong>Notice when it comes back</strong> next week, cropped differently, with a new caption.
          </li>
        </ol>
        <p>
          None of these steps is hard. All of them are slow, and they repeat for every post. During a disaster that
          delay is when misinformation does the most damage: people share the fake while they are frightened, and the
          correction arrives after the fear has passed.
        </p>
        <h3>Two observations</h3>
        <ul>
          <li>
            <strong>Most disaster fakes are not new.</strong> They are old or foreign footage with a new caption. That
            can be proven: if the frames match a 2025 video from Uttarakhand, anyone can see both side by side.
          </li>
          <li>
            <strong>The same fakes come back.</strong> One debunked clip reappears on TikTok, then Facebook, then X. A
            desk that remembers what it has checked never has to check it twice.
          </li>
        </ul>
        <Line>
          Fact-checkers trace every viral disaster post by hand. Hamsa does that searching in about a minute, a person
          decides, and every verdict is remembered, so the same fake is caught at once when it comes back.
        </Line>
        <aside className={`${s.block} ${s.why}`}>
          <span className={s.tag}>The name</span>
          <p>
            In old stories the <span lang="ne">हंस</span> (hamsa, swan) can drink the milk from a mix of milk and water
            and leave the water behind. Nepali calls that judgement <span lang="ne">नीर-क्षीर विवेक</span>. Hamsa does
            the same for a stream of posts, and a person confirms it.
          </p>
        </aside>
      </>
    ),
  },
  {
    slug: "a-triage-desk",
    part: STORY,
    title: "A triage desk, not an oracle",
    lede: "What Hamsa does, what it deliberately does not do, and the four verdicts it uses.",
    body: (
      <>
        <Zero term="triage">
          <p>
            Hospitals triage when there are more patients than doctors: who needs attention now, who can wait. Hamsa
            sorts incoming posts the same way, and prepares each one so a checker starts from evidence instead of an
            empty search box.
          </p>
        </Zero>
        <h3>What it is</h3>
        <ul>
          <li>
            <strong>A way in.</strong> Anyone can send a doubtful post on the website, to a Telegram bot, or to a
            Facebook Page over Messenger. A link is enough.
          </li>
          <li>
            <strong>A preparer.</strong> For every post it pulls out the claim, checks whether the footage has been seen
            before, gathers evidence, and drafts a verdict in Nepali and English with its sources.
          </li>
          <li>
            <strong>A sorter.</strong> Written rules decide where each case goes: one click from publishing when the
            evidence is overwhelming, to a checker when it is not, merged when it is a repeat.
          </li>
          <li>
            <strong>A desk</strong> where a checker sees the post beside the evidence, edits the draft, and publishes.
            Every decision is recorded under the checker&apos;s name.
          </li>
          <li>
            <strong>A memory.</strong> Every published verdict is fingerprinted, so the next copy is recognised.
          </li>
        </ul>
        <h3>What it is not</h3>
        <ul>
          <li>
            <strong>Not an oracle.</strong> Hamsa never publishes on its own. A model&apos;s draft is a proposal; a
            person decides.
          </li>
          <li>
            <strong>Not an &quot;AI detector&quot;.</strong> It does not guess from pixels whether a video was
            generated. Those detectors are unreliable, and wrongly calling a real victim&apos;s video fake is worse than
            missing a fake.
          </li>
        </ul>
        <Zero term="human in the loop">
          <p>
            A system is &quot;human in the loop&quot; when a person makes the final decision on every output. Hamsa
            makes the expensive part, searching and comparing, automatic, and keeps the part that carries
            responsibility, publishing a verdict about someone&apos;s post, human. That split is the whole design.
          </p>
        </Zero>
        <h3>The four verdicts</h3>
        <p>Hamsa uses the labels fact-checkers publish, so its drafts can be compared with their work.</p>
        <dl className={s.verdicts}>
          <div data-label="false">
            <dt>
              <span lang="ne">गलत</span> False
            </dt>
            <dd>The core claim is wrong: footage from elsewhere sold as this disaster, an invented figure.</dd>
          </div>
          <div data-label="misleading">
            <dt>
              <span lang="ne">भ्रामक</span> Misleading
            </dt>
            <dd>Real elements framed to mislead: genuine footage from an older event, a real number out of context.</dd>
          </div>
          <div data-label="true">
            <dt>
              <span lang="ne">सत्य</span> True
            </dt>
            <dd>The claim and the footage hold up.</dd>
          </div>
          <div data-label="unverifiable">
            <dt>
              <span lang="ne">पुष्टि हुन नसकेको</span> Unverifiable
            </dt>
            <dd>The evidence does not settle it either way.</dd>
          </div>
        </dl>
        <Asks
          items={[
            [
              "If a person decides everything, what does the AI do?",
              "Everything before the decision: it reads the post and its frames, finds the claim, compares the footage with everything already checked, searches news and fact-checks in two languages, drafts the verdict, and sorts the case. Each of those outputs changes what happens next.",
            ],
            [
              "Why not let it publish the obvious ones?",
              "A wrong verdict about a real victim's video costs far more than a slow one, and a newsroom's name is on what it publishes. The obvious ones arrive with everything filled in, so publishing takes one click.",
            ],
          ]}
        />
      </>
    ),
  },
  {
    slug: "one-post",
    part: STORY,
    title: "One post, from a phone to a verdict",
    lede: "A real fake from the August floods, followed through every step. Every later chapter looks closer at one of them.",
    body: (
      <>
        <p className={s.story}>
          The post is a TikTok video. A muddy torrent tears through a hillside town, buildings folding into the water.
          On-screen text claims hundreds dead and more than a thousand missing. It is being shared as the Bhotekoshi
          flood. It is not: Newschecker Nepal traced it on 28 August 2026 to the flash flood at Dharali, in India&apos;s
          Uttarakhand, on 5 August 2025.
        </p>
        <JourneyDiagram />
        <ol className={s.timeline}>
          <li>
            <span className={s.when}>Second 0</span>
            <strong>A reader asks.</strong> Someone unsure forwards the link to Hamsa&apos;s Telegram bot. It replies at
            once with a report number and a page that shows how the check is going.
          </li>
          <li>
            <span className={s.when}>Before any AI</span>
            <strong>Is it a repeat?</strong> If this exact link, post or file was reported before, the report joins the
            earlier one, and a published verdict is sent straight back.
          </li>
          <li>
            <span className={s.when}>Seconds</span>
            <strong>The video is fetched,</strong> and up to six keyframes are taken at scene changes: enough to
            recognise the footage, cheap enough to show a model.
          </li>
          <li>
            <span className={s.when}>About 15–30 s</span>
            <strong>The post is read.</strong> A vision model reads the caption and frames and writes down the claim,
            the places, any date, the numbers, the on-screen text and any watermarks.
          </li>
          <li>
            <span className={s.when}>About 1–2 s</span>
            <strong>The footage is compared</strong> with footage of known origin. The match is strong: the same shot
            as Dharali, proven point by point.
          </li>
          <li>
            <span className={s.when}>Seconds</span>
            <strong>Evidence is gathered</strong> from news, fact-checks and the web, and a reasoning model drafts the
            verdict in English and Nepali with its sources.
          </li>
          <li>
            <span className={s.when}>Instant</span>
            <strong>The rules sort it.</strong> False, footage from elsewhere, nothing conflicting: a quick check, at
            the top of the desk.
          </li>
          <li>
            <span className={s.when}>When a checker looks</span>
            <strong>A person decides.</strong> The post&apos;s frame sits beside the Dharali original. The checker
            reads, maybe edits a sentence, and publishes. The reader is told on Telegram.
          </li>
          <li>
            <span className={s.when}>Next week</span>
            <strong>It comes back</strong> as a Facebook reel: a different file on a different platform. Its frames
            match the footage the checker just published, so it arrives ready for one click.
          </li>
        </ol>
        <Num big="About 46 seconds">
          The median time from a post entering Hamsa to a sorted case with a draft, measured on 24 October 2026. Most of
          it is the vision model reading frames on a laptop graphics card.
        </Num>
      </>
    ),
  },
  {
    slug: "fingerprints",
    part: HOW,
    title: "Seeing footage before: three fingerprints",
    lede: "How Hamsa recognises a repost that has been cropped, mirrored or covered in captions, and why it needs three methods.",
    body: (
      <>
        <p>
          A repost is rarely an exact copy. It has been re-encoded by a platform, cropped to a phone screen, mirrored to
          dodge detection, covered with captions, or screenshotted. Comparing files byte by byte finds nothing. So
          Hamsa compares what the frames look like, three different ways.
        </p>
        <FingerprintDiagram />
        <Zero term="a fingerprint">
          <p>
            A fingerprint is a short summary of a picture that stays the same when the picture is changed a little.
            Hamsa stores fingerprints of footage whose origin is known, never the videos, and compares each new frame
            with them.
          </p>
        </Zero>
        <ul>
          <li>
            <strong>A perceptual hash</strong> shrinks a frame to 64 light-and-dark bits. Re-encoding and resizing
            barely change it. It is fast and exact, but a heavy edit breaks it.
          </li>
          <li>
            <strong>An image embedding</strong> from an open model (SigLIP) turns a frame into 768 numbers that describe
            the scene. It still matches under captions and overlays, but on its own it would also match a different
            video of a similar river.
          </li>
          <li>
            <strong>Keypoints</strong> (ORB) are distinctive corners and edges. When dozens of them line up in a
            consistent pattern between two frames, they are the same shot, not just a similar one. This is what stops
            the second method from fooling itself.
          </li>
        </ul>
        <p>
          Mirrored frames are checked too. When there is a match, the checker sees the post&apos;s frame and the original
          side by side, with the original&apos;s date and source. They do not have to trust Hamsa; they can see it.
        </p>
        <Num big="14 of 20">
          Edited copies of flood photos (cropped, mirrored, letterboxed, captioned, screenshotted) matched their
          original, with 0 false matches against five different photos of the same river. The limit was set for safety:
          a looser one matched 17 of 20 but began to confuse unrelated clips.
        </Num>
        <Asks
          items={[
            [
              "What if the footage was never seen before?",
              "Then nothing matches, and that costs nothing. The case is judged on news, fact-checks and the web, and goes to a checker, who has one-click reverse image search on the desk.",
            ],
            [
              "Can't a real video be called old by mistake?",
              "That is why genuine footage only counts as recycled after 30 days: disaster footage is rightly reshared for weeks. And a match is evidence for a checker, not a verdict.",
            ],
          ]}
        />
      </>
    ),
  },
  {
    slug: "evidence",
    part: HOW,
    title: "Finding the evidence, in two languages",
    lede: "Where the sources come from, and why a source that merely mentions the same flood is not enough.",
    body: (
      <>
        <p>
          A verdict is only as good as its sources. Hamsa gathers evidence from four places for every post, and keeps up
          to eight passages, at most two from any one article, so one long report cannot crowd out the rest.
        </p>
        <ul>
          <li>
            <strong>Trusted Nepali news and official sources,</strong> collected every 15 minutes by a news watcher.
          </li>
          <li>
            <strong>Fact-checks published abroad,</strong> through Google&apos;s ClaimReview index, because AFP, BOOM and
            Alt News often debunk the same clips that circulate in Nepal.
          </li>
          <li>
            <strong>The open web,</strong> through a search engine Hamsa runs itself (SearXNG), for events the trusted
            outlets did not cover.
          </li>
          <li>
            <strong>What the platform shows</strong> on the post: a Community Note on X, or TikTok&apos;s
            &quot;AI-generated&quot; label.
          </li>
        </ul>
        <Zero term="cross-lingual search">
          <p>
            A post may be in Nepali and the best report in English, or the other way round. Hamsa turns every passage
            and every claim into numbers that capture meaning (with an open model called bge-m3), so &quot;बाढी&quot; and
            &quot;flood&quot; land in the same place. A search finds meaning, not matching words.
          </p>
        </Zero>
        <h3>Relevant is not the same as related</h3>
        <p>
          Early on, one fact-check roundup about Nepal&apos;s floods was cited against nearly every flood post, because
          its words matched. But a fact-check about a different video of the same flood proves nothing about this one.
          So before a fact-check counts, a model reads it beside the post and answers one question: is this about the
          same footage? If it cannot tell, the fact-check is dropped.
        </p>
        <p>
          Then a reasoning model (gpt-oss, open-weight) reads the claim, the footage match and the passages, and
          drafts the verdict: what it found about the footage, the event and the figures, a label, a confidence, and the
          passages it relied on. A second check makes sure the Nepali says what the English says.
        </p>
        <Line>
          Hamsa searches news, foreign fact-checks, the web and the platform itself in Nepali and English, keeps only
          what is about this post, and cites every passage the draft relies on.
        </Line>
      </>
    ),
  },
  {
    slug: "rules",
    part: HOW,
    title: "Models propose, rules decide",
    lede: "Why the step that decides where a case goes is not an AI model at all.",
    body: (
      <>
        <p>
          Every AI step in Hamsa produces a structured answer: a claim, a match score, a label, a confidence, a list of
          sources. None of them decides what happens next. A short set of written rules reads those answers and decides,
          in the same order, every time.
        </p>
        <RulesDiagram />
        <Zero term="a deterministic rule">
          <p>
            A deterministic rule gives the same answer to the same inputs, every time, and can be read and tested. A
            model can be confidently wrong in ways nobody predicted; a rule can be wrong too, but you can see exactly
            why, and fix it.
          </p>
        </Zero>
        <h3>Why a quick check needs an unfakeable signal</h3>
        <p>
          A model&apos;s confidence is not enough to put a case one click from publishing, because a model can be sure
          and wrong. A quick check needs something independent of the model: the frames matching footage from somewhere
          else, an AI generator&apos;s watermark, a published fact-check that agrees, or two independent trusted sources,
          each on top of a confident draft. Everything else goes to a checker, with the reason it fell short written on the case.
        </p>
        <p>
          When the evidence conflicts (a source that supports the claim against one that refutes it, or a Nepali
          translation that does not match the English), the case always goes to a person, with the conflict shown.
        </p>
        <Line>
          The models answer questions; written, tested rules decide what happens, so every route can be explained and
          nothing reaches the public on a model&apos;s confidence alone.
        </Line>
      </>
    ),
  },
  {
    slug: "memory",
    part: HOW,
    title: "A memory, not a library",
    lede: "How Hamsa gets better with use without retraining, and how it can grow past one newsroom.",
    body: (
      <>
        <p>
          Every verdict a checker publishes, true or false, is fingerprinted into Hamsa&apos;s archive, and so is any
          original footage a checker finds by hand. The next copy of that footage, even re-encoded, cropped or
          re-captioned, is recognised without anyone searching. An exact repeat of a link is answered at once with the
          published verdict.
        </p>
        <Zero term="remembering versus retraining">
          <p>
            Retraining changes a model&apos;s insides, and nobody can point to why it now answers differently. Hamsa
            does not retrain. It remembers: every match points to a verdict a named person published, so every decision
            stays traceable.
          </p>
        </Zero>
        <h3>It does not need to know everything</h3>
        <p>
          A fair worry: the archive starts small, and a newsroom would need years of footage to make it complete. But
          it never has to be complete. Footage nobody has checked goes to a person anyway. The archive only has to know
          what checkers have already decided, and that grows with every verdict.
        </p>
        <h3>Growing past one desk</h3>
        <p>
          The archive stores fingerprints, about 100 KB per keyframe, never the videos. That makes them easy to share.
          If newsrooms exchanged fingerprints with their label and a link to the verdict, a fake debunked at one desk
          would be caught at every other. Platforms already fight known harmful media this way, sharing hashes rather
          than content. Each desk would choose whose verdicts it trusts.
        </p>
        <Line>
          Hamsa does not store the world&apos;s videos; it remembers what checkers have verified, and shared between
          newsrooms, one checker&apos;s verdict could protect every desk.
        </Line>
      </>
    ),
  },
  {
    slug: "under-the-hood",
    part: HOW,
    title: "Under the hood: one laptop, open models",
    lede: "What runs where, and why every model is one anyone can download.",
    body: (
      <>
        <SystemDiagram />
        <h3>Open models, end to end</h3>
        <p>
          Every model in Hamsa is open-weight: its weights are published, and anyone can download and run it. A newsroom
          in Nepal has nothing to subscribe to, nothing that stops working when a foreign company changes its prices,
          and no reason to send someone&apos;s footage off its own machine.
        </p>
        <div className={s.tableWrap}>
          <table>
            <thead>
              <tr>
                <th scope="col">Job</th>
                <th scope="col">Model</th>
                <th scope="col">Where</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>Read the post and its frames</td>
                <td>Qwen3-VL-8B</td>
                <td>the laptop&apos;s GPU</td>
              </tr>
              <tr>
                <td>Search by meaning, find duplicates</td>
                <td>bge-m3</td>
                <td>CPU</td>
              </tr>
              <tr>
                <td>Match footage</td>
                <td>SigLIP 2, with pHash and ORB</td>
                <td>CPU</td>
              </tr>
              <tr>
                <td>Draft the verdict, check fact-checks and Nepali</td>
                <td>gpt-oss-120b and 20b</td>
                <td>Groq (optional), or the local model</td>
              </tr>
            </tbody>
          </table>
        </div>
        <h3>Built for a small machine</h3>
        <ul>
          <li>
            <strong>The graphics card is for the vision model only.</strong> With 8 GB of video memory, everything else
            runs on the processor.
          </li>
          <li>
            <strong>One worker, one case at a time,</strong> from a queue in an ordinary SQLite file. If anything
            crashes, the case is picked up again; nothing is lost.
          </li>
          <li>
            <strong>Every model answer is checked against a strict format.</strong> An answer that does not fit is
            retried, falls back to the local model, or goes to a person.
          </li>
          <li>
            <strong>One command</strong> (<code>docker compose up</code>) starts the API, worker, news watcher, website
            and vector store.
          </li>
        </ul>
        <Asks
          items={[
            [
              "Isn't Groq a cloud service?",
              "Groq hosts gpt-oss, an open-weight model, on its free tier. Without a Groq key every model runs on the laptop; drafts are weaker, so none of them is ever a quick check.",
            ],
            [
              "Where can I see every model call?",
              <>
                The README lists each one with the file and function that uses its output:{" "}
                <a href={`${REPO}#ai-usage-disclosure`}>AI usage disclosure</a>.
              </>,
            ],
          ]}
        />
      </>
    ),
  },
  {
    slug: "the-numbers",
    part: PROOF,
    title: "The numbers, and what went wrong",
    lede: "How Hamsa was tested, what came out, and the failures, named first.",
    body: (
      <>
        <Zero term="an evaluation set">
          <p>
            To know whether a system is right, you need cases where the right answer is already known, chosen
            independently of the system. Hamsa&apos;s answers come from published fact-checks, with their links, and
            for genuine posts from established outlets. Media is never taken from a fact-check article, since its
            &quot;FALSE&quot; stamp would give the answer away.
          </p>
        </Zero>
        <p>
          The most important number is <strong>quick-check precision</strong>: of the cases put one click from
          publishing, how many had the right verdict. A wrong one there is the costliest mistake.
        </p>
        <div className={s.figures}>
          <div>
            <b>8 of 8</b>
            <span>quick checks right on the labelled set</span>
          </div>
          <div>
            <b>7 of 7</b>
            <span>quick checks right on 88 real posts sent to Hamsa</span>
          </div>
          <div>
            <b>9 of 9</b>
            <span>&quot;this footage is from elsewhere&quot; calls right</span>
          </div>
        </div>
        <div className={s.tableWrap}>
          <table>
            <thead>
              <tr>
                <th scope="col">Posts</th>
                <th scope="col">Quick checks right</th>
                <th scope="col">Fake or not, right</th>
                <th scope="col">Exact label</th>
                <th scope="col">Sent to a person</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <th scope="row">Labelled set (40)</th>
                <td>8 / 8</td>
                <td>31 / 40</td>
                <td>21 / 40</td>
                <td>31 / 40</td>
              </tr>
              <tr>
                <th scope="row">Real posts (88)</th>
                <td>7 / 7</td>
                <td>57 / 88</td>
                <td>45 / 88</td>
                <td>78 / 88</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p className={s.small}>Fresh run on 24 October 2026; real posts scored on 25 October 2026.</p>
        <h3>Reading them honestly</h3>
        <ul>
          <li>
            <strong>Most posts go to a person, on purpose.</strong> Quick checks are kept for signals that cannot be
            faked. Everything else arrives drafted, with its evidence.
          </li>
          <li>
            <strong>Exact labels are lower partly by design.</strong> Fact-checkers themselves disagree: Nepal Factcheck
            usually rates foreign footage passed off as Nepal &quot;misleading&quot;, AFP rates it &quot;false&quot;. And
            Hamsa prefers &quot;unverifiable&quot; to a guess.
          </li>
          <li>
            <strong>Time saved has not been measured</strong> with a professional fact-checker. What is measured is that
            most cases reach the desk in under a minute, with the original footage, sources and a bilingual draft.
          </li>
        </ul>
        <h3>What went wrong</h3>
        <ul>
          <li>
            A genuine news clip of a rescuer describing a rescue was judged &quot;not a checkable claim&quot; and never
            reached a checker. No false post was cleared, but a true one should have reached a person.
          </li>
          <li>
            Three early real posts were wrongly merged or dismissed because a TikTok fetching bug made different posts
            look like the same file. Fixed on 22 October 2026.
          </li>
          <li>
            The held-out test set is small (4 posts), which is why the 88 real posts were sent through Hamsa exactly as
            a reader would.
          </li>
        </ul>
      </>
    ),
  },
  {
    slug: "limits",
    part: PROOF,
    title: "What Hamsa does not do yet",
    lede: "Where it stops today, and what comes next, in the order the evidence points to.",
    body: (
      <>
        <ul>
          <li>
            <strong>Recognise footage nobody has checked.</strong> New footage has nothing to match. It is judged on
            news, fact-checks and the web, and always reaches a person first.
          </li>
          <li>
            <strong>Reverse-search every image automatically.</strong> No free API for that exists. Checkers keep
            one-click Google Lens, Yandex and TinEye, and Hamsa remembers what they find.
          </li>
          <li>
            <strong>Open private or deleted posts.</strong> The sender is asked for the photo or video instead.
          </li>
          <li>
            <strong>Match every repost style.</strong> A video placed over a blurred copy of itself, common on TikTok,
            is not matched yet.
          </li>
          <li>
            <strong>Work beyond disasters.</strong> Only the news filter, a few prompt lines and one rule know about
            disasters. But each new topic, such as elections or health, needs its own tested examples before any quick
            check is trusted.
          </li>
          <li>
            <strong>Run in a newsroom, yet.</strong> No fact-checking desk has used Hamsa in daily work so far.
          </li>
        </ul>
        <h3>What comes next</h3>
        <ol>
          <li>Send &quot;not checkable&quot; posts that carry disaster footage to a person instead of dismissing them.</li>
          <li>Grow the held-out test set, and keep scoring real posts as checkers publish.</li>
          <li>Match videos placed over blurred copies of themselves.</li>
          <li>Share fingerprints between newsrooms.</li>
          <li>Read Content Credentials (C2PA) where a camera or editor has signed the media.</li>
          <li>A WhatsApp tipline, more languages (Maithili, Bhojpuri), and topics beyond disasters.</li>
        </ol>
        <aside className={`${s.block} ${s.line}`}>
          <span className={s.tag}>Read further</span>
          <p>
            The code, test data and every design decision are public on <a href={REPO}>GitHub</a>, starting with the{" "}
            <a href={`${REPO}#readme`}>README</a>, the <a href={`${REPO}/blob/develop/docs/architecture.md`}>architecture</a>{" "}
            and the <a href={`${REPO}/tree/develop/docs/adr`}>decision records</a>.
          </p>
        </aside>
      </>
    ),
  },
];
