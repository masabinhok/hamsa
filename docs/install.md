# Installing Hamsa at a fact-checking desk

This guide is for the person who sets Hamsa up for a newsroom or fact-checking team. It takes about an hour, most of it downloads.

## What you need

- **A Linux computer that stays on**, with an NVIDIA GPU with 8 GB of memory or more, 16 GB of RAM, and 60 GB of free disk. Hamsa runs fully on this machine; posts and verdicts never leave it except for the verdict and Nepali checks sent to Groq.
- **Docker** with the compose plugin.
- **[Ollama](https://ollama.com)** for the local models. It runs outside Docker because it needs the GPU.
- **A free [Groq](https://console.groq.com) API key** for the verdict model (open-weight gpt-oss). Without it, verdicts run on the local model, which is weaker and never fast-tracked.
- **Firefox, signed in to Facebook and TikTok** with an account the desk uses. Hamsa borrows that login to open links readers send (ADR 0010). YouTube needs no login.

## Set it up

```bash
git clone https://github.com/masabinhok/hamsa.git && cd hamsa

# Local models: the vision model reads posts, bge-m3 searches the news.
ollama pull qwen3-vl:8b-instruct
ollama pull bge-m3

cp .env.example .env
# In .env: set GROQ_API_KEY, and FETCH_BROWSER=firefox to open Facebook and TikTok links.

docker compose up -d --build
```

This starts five services: the vector store (`qdrant`), the API, the worker that checks posts, the corpus watcher that adds new articles every 15 minutes, and the website.

### Build the evidence and the archive (first time only)

```bash
docker compose run --rm worker python -m app.corpus fetch    # the last 30 days of news and all fact-checks, ~2 min
docker compose run --rm worker python -m app.corpus index    # embed them, ~15 min on the GPU
docker compose run --rm worker python -m app.archive         # index the starting footage archive
```

From then on the corpus watcher keeps the news current, and the archive grows by itself from every published verdict (ADR 0011).

### Give each fact-checker an account

```bash
docker compose run --rm worker python -m app.checkers add "Sita Sharma"
```

This prints Sita's access code once. Give it to her privately; Hamsa keeps only a hash of it. `list` shows everyone, and `remove "Sita Sharma"` locks a code out, for example when someone leaves.

## Use it

- **Public page:** `http://localhost:3000`. Readers paste a link or upload a photo or video and get a report page that updates when a verdict is published. To open it to the public, put it behind your usual web server with HTTPS.
- **Checker desk:** `http://localhost:3000/desk`. Sign in with an access code. Cases arrive sorted: ready to publish, needs a checker, new claims.
  - When you refute a recycled post, paste where you found the original into "Original found at". Hamsa remembers that footage, and its next reposts are recognised without anyone searching.

### Telegram bot (optional)

Readers can forward doubtful posts to a Telegram bot instead of opening the website.

1. In Telegram, message [@BotFather](https://t.me/BotFather), send `/newbot`, and follow the steps. It gives you a token.
2. In `.env`, set `TELEGRAM_BOT_TOKEN` to that token, and `FRONTEND_ORIGIN` to the public address of your site, since the bot's report links point there.
3. Start it: `docker compose --profile telegram up -d`.

The bot replies to each post with its report link, and messages the reader again when a verdict is published. `docker compose logs -f telegram` shows what it receives.

## Look after it

| Task | Command |
|---|---|
| See what the worker is doing | `docker compose logs -f worker` |
| Stop everything | `docker compose down` |
| Update to a new version | `git pull && docker compose up -d --build` |
| Back up | copy the `data/` folder: cases, verdicts, archive, and evidence |

## Known limits

- **Linux only.** The backend uses host networking to reach Ollama.
- **Links to private or deleted posts** cannot be opened; the report page (and the Telegram bot) asks the reader for the file instead.
- **Telegram files over 20 MB** are not passed to bots; the bot asks for the post's link instead.
- **The first report of new footage still needs a checker.** Hamsa recognises footage it has seen before; it does not search the web for originals (ADR 0011 explains why).
