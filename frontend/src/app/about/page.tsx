import type { Metadata } from "next";
import { Masthead } from "@/components/Site";
import styles from "./about.module.css";

const REPO = "https://github.com/masabinhok/hamsa";

export const metadata: Metadata = {
  title: "About Hamsa (हंस): how it works",
  description:
    "Why Hamsa exists, how it checks a disaster post in about a minute, why a person always decides, and how well it has done on real posts.",
};

const contents: [string, string][] = [
  ["why", "Why Hamsa exists"],
  ["what", "What Hamsa is, and is not"],
  ["journey", "One post, start to finish"],
  ["footage", "How it recognises old footage"],
  ["evidence", "Where the evidence comes from"],
  ["person", "Why a person always decides"],
  ["memory", "It remembers"],
  ["proof", "How well it works"],
  ["limits", "What it does not do yet"],
  ["open", "Open by design"],
];

// The four labels fact-checkers publish; the colours match the verdict tags on the site.
const verdicts: [string, string, string, string][] = [
  ["false", "False", "गलत", "The core claim is wrong: footage from elsewhere sold as this disaster, an invented figure."],
  ["misleading", "Misleading", "भ्रामक", "Real elements framed to mislead: genuine footage from an older event, a real number out of context."],
  ["true", "True", "सत्य", "The claim and the footage hold up."],
  ["unverifiable", "Unverifiable", "पुष्टि हुन नसकेको", "The evidence does not settle it either way."],
];

// L03 from the live test set, as it went through Hamsa.
const journey: [string, string, string][] = [
  ["Second 0", "A reader asks", "Someone unsure about the video forwards its link to Hamsa's Telegram bot. The bot replies at once with a report number and a link to a page that shows how the check is going."],
  ["Before any AI", "Is it a repeat?", "Hamsa first asks whether this exact link, post or file has been reported before. If it has, the report joins the earlier one, and if that one already has a verdict, the reader gets it straight away."],
  ["Seconds", "The video is fetched", "Hamsa downloads the video behind the link and takes up to six keyframes at scene changes, enough to recognise the footage."],
  ["About 15–30 s", "The post is read", "A vision model reads the caption and the frames and writes down the claim: what is said, where, when, the numbers (\"1,000+ missing\"), the on-screen text, and any watermarks or account names."],
  ["About 1–2 s", "The footage is compared", "Each frame is matched against footage with a known origin. Here the match is strong: the same shot as the Dharali flood in India's Uttarakhand, 5 August 2025."],
  ["Seconds", "Evidence is gathered", "News in Nepali and English, fact-checks published in Nepal and abroad, and the open web. Up to eight passages are kept."],
  ["Seconds", "A verdict is drafted", "A reasoning model weighs the claim, the footage match and the evidence, and drafts a verdict in English and Nepali with its sources. A second check makes sure the Nepali says what the English says."],
  ["Instant", "The case is sorted", "Fixed rules, not a model, decide where the case goes. A strong match to footage from elsewhere, a false verdict and no conflicting evidence: it goes to the top of the desk as a quick check."],
  ["When a checker looks", "A person decides", "The checker sees the post's frame beside the Dharali original, the draft and its sources. They read it, edit a sentence if needed, and publish. The decision is recorded under their name."],
  ["Seconds later", "The reader hears back", "The bot sends the verdict in Nepali and English, with sources and the report link."],
  ["Next week", "The fake comes back", "Someone sends the same clip as a Facebook reel, a different file on a different platform. Its frames match the footage the checker just published, so it arrives on the desk ready for one click."],
];

export default function About() {
  return (
    <div className={styles.page}>
      <Masthead />
      <main className={styles.main} lang="en">
        <header className={styles.hero}>
          <p className={styles.kicker}>About Hamsa</p>
          <h1 className={styles.title}>
            A fact-check desk that does the searching, so people can do the deciding
          </h1>
          <p className={styles.lede}>
            Hamsa helps fact-checkers in Nepal answer doubtful disaster posts in minutes instead of hours. It finds where
            a video really came from, gathers the evidence, and drafts a verdict in Nepali and English. A fact-checker
            reads it and decides. Nothing is published without them.
          </p>
        </header>

        <nav className={styles.contents} aria-labelledby="contents-title">
          <h2 id="contents-title">Contents</h2>
          <ol>
            {contents.map(([id, title]) => (
              <li key={id}>
                <a href={`#${id}`}>{title}</a>
              </li>
            ))}
          </ol>
        </nav>

        <section id="why" className={styles.section}>
          <h2>Why Hamsa exists</h2>
          <p>
            Early on 26 August 2026, a flood came down the Bhotekoshi river in Rasuwa. Within days the official count
            passed 900 dead, with thousands missing. Within hours, social media filled with flood videos. Many were
            real. Many were not: a 2025 flash flood in India&apos;s Uttarakhand went round as &quot;Bhotekoshi
            today&quot;, a glacier collapse filmed in Alaska became &quot;the moment the glacier burst in Rasuwa&quot;,
            and AI-made videos showed bridges folding into rivers.
          </p>
          <p>
            The Nepal Press Council&apos;s reporting portal received 101 complaints within days. Fact-checkers traced
            each one by hand, and by hand means the same steps every time:
          </p>
          <ol className={styles.steps}>
            <li>Work out what is actually being claimed.</li>
            <li>Check whether the footage has appeared before, frame by frame, in reverse image search.</li>
            <li>Search for evidence: news from the right dates, official figures, fact-checks published elsewhere.</li>
            <li>Write the verdict, in Nepali for the public and often in English too.</li>
            <li>Notice when the same fake comes back next week, cropped and re-captioned.</li>
          </ol>
          <p>
            None of this is hard. All of it is slow, and it is repeated for every post. During a disaster, that delay
            is when misinformation does the most damage: people share the fake while they are frightened, and the
            correction arrives after the fear has passed.
          </p>
          <p>Two observations shaped Hamsa:</p>
          <ul className={styles.points}>
            <li>
              <strong>Most disaster fakes are not new.</strong> They are old or foreign footage with a new caption. That
              can be proven: if the frames match a 2025 video from Uttarakhand, anyone can see both side by side.
            </li>
            <li>
              <strong>The same fakes come back.</strong> One debunked clip reappears on TikTok, then Facebook, then X. A
              desk that remembers what it has checked never has to check it twice.
            </li>
          </ul>
          <aside className={styles.note}>
            <h3>The name</h3>
            <p>
              In old stories the हंस (hamsa, swan) can drink the milk from a mix of milk and water and leave the water
              behind. Nepali calls that judgement नीर-क्षीर विवेक. Hamsa does the same for a stream of posts, and a
              person confirms it.
            </p>
          </aside>
        </section>

        <section id="what" className={styles.section}>
          <h2>What Hamsa is, and is not</h2>
          <p>
            Hamsa is a <strong>triage desk</strong>. Triage is how a hospital sorts patients when there are more of
            them than doctors. Hamsa sorts incoming posts the same way, and prepares each one so a checker starts from
            evidence instead of an empty search box.
          </p>
          <ul className={styles.points}>
            <li>
              <strong>Anyone can send a post</strong> on the website, to a Telegram bot, or to a Facebook Page over
              Messenger. A link is enough.
            </li>
            <li>
              <strong>Every post is prepared:</strong> the claim, where the footage came from, the evidence, and a
              drafted verdict in two languages.
            </li>
            <li>
              <strong>A checker decides</strong> at the desk, and the person who sent the post is told on the channel
              they used.
            </li>
            <li>
              <strong>Every verdict is remembered,</strong> so the next copy of that footage is recognised.
            </li>
          </ul>
          <p>
            It is <strong>not an oracle</strong>: it never publishes on its own. It is <strong>not an &quot;AI
            detector&quot;</strong>: it does not guess from pixels whether a video was generated, because those tools
            are unreliable, and wrongly calling a real victim&apos;s video fake is worse than missing a fake.
          </p>
          <h3>The four verdicts</h3>
          <p>Hamsa uses the same labels fact-checkers publish, so its drafts can be compared with their work.</p>
          <dl className={styles.verdicts}>
            {verdicts.map(([key, en, ne, meaning]) => (
              <div key={key} data-label={key}>
                <dt>
                  <span lang="ne">{ne}</span> {en}
                </dt>
                <dd>{meaning}</dd>
              </div>
            ))}
          </dl>
        </section>

        <section id="journey" className={styles.section}>
          <h2>One post, start to finish</h2>
          <p>
            A real fake from the August floods: a TikTok video of a muddy torrent tearing through a hillside town, with
            on-screen text claiming hundreds dead and more than a thousand missing, shared as the Bhotekoshi flood.
            Newschecker Nepal traced it on 28 August 2026 to the flash flood at Dharali, in India&apos;s Uttarakhand,
            on 5 August 2025. Here is what Hamsa does with it.
          </p>
          <ol className={styles.timeline}>
            {journey.map(([when, what, detail]) => (
              <li key={what}>
                <span className={styles.when}>{when}</span>
                <h3>{what}</h3>
                <p>{detail}</p>
              </li>
            ))}
          </ol>
          <p>
            From the moment a post enters Hamsa to the moment it waits on the desk with a draft takes{" "}
            <strong>about 46 seconds</strong> for half of all posts. Most of that is the vision model reading frames on
            a laptop graphics card.
          </p>
        </section>

        <section id="footage" className={styles.section}>
          <h2>How it recognises old footage</h2>
          <p>
            Reposts are rarely exact copies. They are re-encoded, cropped, mirrored, covered with captions or
            screenshotted. So Hamsa fingerprints every keyframe three different ways, each catching what the others
            miss:
          </p>
          <ul className={styles.points}>
            <li>
              <strong>A perceptual hash</strong> is a short summary of what a picture looks like. It survives
              re-encoding, resizing and light crops.
            </li>
            <li>
              <strong>An image embedding</strong> describes the scene itself, so it still matches under captions,
              overlays and heavier edits.
            </li>
            <li>
              <strong>Keypoint matching</strong> then proves the two frames are the same shot, point by point, and not
              just a similar river. Mirrored frames are checked too.
            </li>
          </ul>
          <p>
            When there is a match, the checker sees the post&apos;s frame and the original side by side, with the
            original&apos;s date and source. They do not have to trust Hamsa; they can see it.
          </p>
        </section>

        <section id="evidence" className={styles.section}>
          <h2>Where the evidence comes from</h2>
          <ul className={styles.points}>
            <li>
              <strong>Trusted Nepali news and official sources</strong>, searched in Nepali and English at once, so an
              English claim finds a Nepali report and the other way round.
            </li>
            <li>
              <strong>Fact-checks published abroad</strong>, such as AFP, BOOM and Alt News, which often debunk the
              same clips. Each one is checked against the post before it counts, because a fact-check about a
              different video of the same flood proves nothing.
            </li>
            <li>
              <strong>The open web</strong>, through a search engine Hamsa runs itself.
            </li>
            <li>
              <strong>What the platform shows</strong> on the post, such as a Community Note on X or TikTok&apos;s
              &quot;AI-generated&quot; label.
            </li>
          </ul>
          <p>Every passage the draft relies on is cited, so the checker can open it and read it.</p>
        </section>

        <section id="person" className={styles.section}>
          <h2>Why a person always decides</h2>
          <p>
            A wrong verdict about a real victim&apos;s video costs far more than a slow one, and a newsroom&apos;s name
            is on everything it publishes. So Hamsa automates the searching and keeps the deciding human.
          </p>
          <p>
            A small set of <strong>fixed, written rules</strong> sorts each case. The rules act on what the AI found,
            but they are not themselves AI, so every decision can be explained:
          </p>
          <ul className={styles.points}>
            <li>
              <strong>Quick check:</strong> only when the evidence is overwhelming, such as a strong match to footage
              from elsewhere with nothing that conflicts. It still waits for one click from a checker.
            </li>
            <li>
              <strong>Needs a checker:</strong> anything ambiguous, with the reason shown and the evidence side by
              side.
            </li>
            <li>
              <strong>Repeat:</strong> merged into the report already on the desk.
            </li>
          </ul>
        </section>

        <section id="memory" className={styles.section}>
          <h2>It remembers</h2>
          <p>
            Every verdict a checker publishes, true or false, is fingerprinted into Hamsa&apos;s archive, and so is
            any original footage a checker finds by hand. The next copy of that footage, even re-encoded, cropped or
            re-captioned, is recognised without anyone searching. An exact repeat of a link is answered at once with
            the published verdict.
          </p>
          <p>
            Hamsa remembers; it does not retrain itself. Every match points to a verdict a named person published, so
            every decision stays traceable.
          </p>
          <p>
            The archive stores fingerprints, about 100 KB per keyframe, never the videos. That is how it can grow past
            one newsroom: desks could share fingerprints and labels with each other, the way platforms already share
            hashes of known harmful media, so one checker&apos;s verdict protects every desk.
          </p>
        </section>

        <section id="proof" className={styles.section}>
          <h2>How well it works</h2>
          <p>
            Hamsa was tested on posts whose answer was already known from published fact-checks, never from Hamsa
            itself. The most important number is the <strong>quick-check precision</strong>: of the cases Hamsa put
            one click from publication, how many had the right verdict.
          </p>
          <div className={styles.figures}>
            <p>
              <strong>8 of 8</strong> quick checks right on the tuning set
            </p>
            <p>
              <strong>7 of 7</strong> quick checks right on 88 real posts sent to Hamsa
            </p>
            <p>
              <strong>9 of 9</strong> &quot;this footage is from elsewhere&quot; calls right
            </p>
          </div>
          <div className={styles.tableWrap}>
            <table>
              <caption>Fresh run on 24 October 2026, and real posts scored on 25 October 2026</caption>
              <thead>
                <tr>
                  <th scope="col">Posts</th>
                  <th scope="col">Quick checks right</th>
                  <th scope="col">Fake or not, right</th>
                  <th scope="col">Exact label right</th>
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
          <h3>Reading the numbers honestly</h3>
          <ul className={styles.points}>
            <li>
              <strong>Most posts go to a person, on purpose.</strong> Quick checks are kept for cases with a signal
              that cannot be faked. Everything else arrives drafted, with its evidence.
            </li>
            <li>
              <strong>Exact labels are lower partly by design.</strong> Fact-checkers themselves disagree on
              &quot;false&quot; versus &quot;misleading&quot; for the same kind of post, and Hamsa prefers
              &quot;unverifiable&quot; to a guess.
            </li>
            <li>
              <strong>Time saved has not been measured</strong> with a professional fact-checker yet. What is measured
              is that a case reaches the desk in under a minute for most posts, with the original footage, sources and
              a bilingual draft already attached.
            </li>
          </ul>
          <h3>What went wrong</h3>
          <ul className={styles.points}>
            <li>
              A genuine news clip of a rescuer describing a rescue was judged &quot;not a checkable claim&quot; and
              never reached a checker. No false post was cleared, but a true one should have reached a person.
            </li>
            <li>
              Three early real posts were wrongly merged or dismissed because of a TikTok fetching bug, fixed on 22
              October 2026.
            </li>
            <li>The held-out test set is small (4 posts), which is why the real-post test exists.</li>
          </ul>
        </section>

        <section id="limits" className={styles.section}>
          <h2>What it does not do yet</h2>
          <ul className={styles.points}>
            <li>
              <strong>Recognise footage nobody has checked.</strong> New footage has nothing to match, so it is judged
              on news, fact-checks and the web, and always reaches a person first.
            </li>
            <li>
              <strong>Reverse-search every image automatically.</strong> No free API for that exists. The checker
              keeps one-click Google Lens, Yandex and TinEye, and Hamsa remembers what they find.
            </li>
            <li>
              <strong>Open private or deleted posts.</strong> The sender is asked for the photo or video instead.
            </li>
            <li>
              <strong>Match every repost style.</strong> Videos placed on a blurred copy of themselves, common on
              TikTok, are not matched yet.
            </li>
            <li>
              <strong>Cover topics beyond disasters.</strong> The engine is not tied to disasters, but each new topic
              needs its own tested examples before any quick check is trusted.
            </li>
            <li>
              <strong>Run in a newsroom, yet.</strong> No fact-checking desk has used Hamsa in daily work so far.
            </li>
          </ul>
        </section>

        <section id="open" className={styles.section}>
          <h2>Open by design</h2>
          <p>
            Every AI model in Hamsa is open-weight: anyone can download and run it. Hamsa runs on one laptop with an
            8 GB graphics card, and every model can run on that laptop, with no cloud AI service at all. A newsroom in Nepal has nothing to subscribe to,
            nothing that stops working when a foreign company changes its prices, and no reason to send media off its
            own machine.
          </p>
          <p>
            The code, the test data, the design decisions and a list of every model call are public. Read them on{" "}
            <a href={REPO}>GitHub</a>, starting with the <a href={`${REPO}#readme`}>README</a> and the{" "}
            <a href={`${REPO}/blob/develop/docs/architecture.md`}>architecture</a>.
          </p>
        </section>
      </main>
    </div>
  );
}
