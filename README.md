# 🏆 Hackathon Alert Automation

> Never miss a hackathon in Hyderabad again. A fully automated, zero-cost pipeline that finds new hackathons twice a day, ranks them for B.Tech students, and delivers a clean digest straight to Telegram.

![Python](https://img.shields.io/badge/python-3.11+-blue.svg)
![GitHub Actions](https://img.shields.io/badge/runs%20on-GitHub%20Actions-2088FF.svg)
![Telegram](https://img.shields.io/badge/delivery-Telegram-26A5E4.svg)
![Cost](https://img.shields.io/badge/cost-%240-brightgreen.svg)

## ✨ What it does

Twice a day (**7:30 AM IST** and **6:30 PM IST**) the bot:

1. **Collects** hackathons from Unstop (primary) and other trusted platforms
2. **Enriches** messy descriptions with Gemini to extract venue, accommodation, team size, eligibility, and perks
3. **Ranks** events, prioritizing B.Tech eligibility, final-year-friendly events, free entry, internship/PPO opportunities, and reputed organizers
4. **Sends** one digest to Telegram containing only **new** hackathons you haven't seen before

If nothing new turns up, it stays silent.

## 📬 What the digest looks like

The digest has two sections:

**Section A: Hyderabad Hackathons** (offline and hybrid, entire Hyderabad area)
**Section B: High-Popularity Picks** (big prize pools, reputed organizers, online events)

Each hackathon shows:

| Field | Example |
|---|---|
| 🏆 Title | Smart India Hackathon Internal Round |
| 🏢 Hosted by | Organizer / college / company |
| 📍 Venue | Venue and mode (offline / hybrid / online) |
| 📅 Dates | Event start to end |
| ⏳ Apply within | Days left plus deadline date |
| 💰 Entry fee | Free or ₹ amount |
| 👥 Team / Solo | Team size range, or "Solo only" / "Team only" |
| 🏨 Accommodation | Yes / No / Not specified |
| 🎁 Prize & perks | Prize pool, internship/PPO, certificates |
| 🎓 Eligibility | B.Tech year or branch restrictions |
| 🔗 Register | One-tap button to the registration page |

Events closing within 48 hours get a **🔥 Closing soon** tag, and are re-alerted once as a "last call".

> Digests longer than Telegram's 4,096-character limit are split automatically into sequential messages, never mid-hackathon.

## 🏗️ Architecture

```
GitHub Actions (cron, 2x/day)
        │
        ▼
   main.py (orchestrator)
        │
        ├── sources/        Unstop, Devfolio, Devpost, MLH, HackerEarth
        ├── enrich.py       Gemini extracts fields + one-line summary
        ├── ranker.py       weighted scoring (config.yaml)
        ├── storage.py      SQLite dedup + enrichment cache
        ├── formatters/     Telegram HTML digest
        └── notifiers/      Telegram (active) · Email (add-on) · WhatsApp (stub)
```

Each source runs in isolation, so one broken scraper never stops the run.

## 🚀 Setup (about 15 minutes)

### 1. Create the Telegram bot

1. Open Telegram and message [@BotFather](https://t.me/BotFather)
2. Send `/newbot`
3. Display name: `Hackathon Alert Automation`
4. Username: `HackathonAlert_bot` (usernames are globally unique; if taken, try `HackathonAlertHyd_bot`)
5. Copy the **bot token** and keep it private

### 2. Get your chat ID

1. Send any message (e.g. "hi") to your new bot
2. Open `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`
3. Find `"chat":{"id": ...}` and copy that number

### 3. Get a Gemini API key

Create a free key at [Google AI Studio](https://aistudio.google.com/).

### 4. Fork and configure the repo

1. Fork or clone this repo
2. Go to **Settings → Secrets and variables → Actions** and add:

| Secret | Value |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Token from BotFather |
| `TELEGRAM_CHAT_ID` | Your chat ID |
| `GEMINI_API_KEY` | Your Gemini key |

3. Go to the **Actions** tab and enable workflows
4. Run **"Hackathon Digest"** once manually (**Run workflow**) to verify the first digest arrives

After that it runs on its own, twice a day.

## 💻 Run locally

```bash
git clone https://github.com/<your-username>/hackathon-alert-automation.git
cd hackathon-alert-automation
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env    # then fill in your keys
```

```bash
python main.py --dry-run          # prints the digest, sends nothing
python main.py                    # real run
python main.py --force-resend     # ignore dedup, resend everything
pytest                            # run tests
```

## ⚙️ Configuration (`config.yaml`)

| Setting | What it controls |
|---|---|
| `sources` | Turn each platform on or off |
| `cities` | Locations counted as "Hyderabad" (Secunderabad, Gachibowli, HITEC City, Madhapur, etc.) |
| `top_n` | Max events per section (default: 10 for Hyderabad, 5 for popular picks) |
| `weights` | Ranking weights: B.Tech eligibility, final-year bonus, free entry, internship/PPO, organizer reputation, prize pool, deadline urgency, accommodation |
| `organizer_whitelist` | Organizers treated as reputed |
| `notifiers` | Enable or disable Telegram, email, WhatsApp |

## 📈 How ranking works

Events are scored by a weighted sum. Higher priority goes to:

1. **B.Tech eligibility** (non-eligible events always rank below eligible ones)
2. **Final-year-friendly** events
3. **Free entry**
4. **Internship / PPO / job opportunities**
5. **Reputed organizers**
6. **Prize pool**
7. **Deadline urgency** (small bonus at 3 days or fewer)
8. **Accommodation provided**

All weights are editable in `config.yaml`.

## ➕ Add-ons

### Email digest (disabled by default)

The email notifier is fully implemented but switched off. To enable it:

1. Create a Gmail [App Password](https://support.google.com/accounts/answer/185833) (requires 2-step verification)
2. Add these secrets: `SMTP_USER`, `SMTP_APP_PASSWORD`, `EMAIL_TO`
3. Set `notifiers.email.enabled: true` in `config.yaml`

### WhatsApp

A documented stub exists in `notifiers/whatsapp_stub.py`. Reliable WhatsApp delivery requires a paid provider or an unofficial library that violates WhatsApp's terms, so it is intentionally not implemented.

### Adding a new source

1. Create `sources/yoursource.py` extending the `Source` base class in `sources/base.py`
2. Implement `fetch()` to return normalized hackathons
3. Add a fixture and test under `tests/`
4. Enable it in `config.yaml`

## 🗂️ Project structure

```
hackathon-alert-automation/
├── main.py
├── config.yaml
├── sources/          # one module per platform
├── enrich.py         # Gemini extraction
├── models.py         # normalized Hackathon schema
├── ranker.py
├── storage.py        # SQLite dedup + cache
├── formatters/
├── notifiers/
├── tests/
└── .github/workflows/digest.yml
```

## 🔒 Security

- Never commit `.env` or tokens. Secrets live in GitHub Secrets.
- If a token leaks, revoke it in BotFather with `/revoke` and update the secret.

## ⚠️ Responsible scraping

This project reads publicly available listing data at a low rate (twice daily, with delays and backoff). It does not bypass logins or CAPTCHAs. Platforms can change their pages or terms at any time, so:

- Check each platform's terms of service before using this
- Keep the schedule modest
- Expect occasional scraper maintenance when a site changes

This is an independent project and is not affiliated with Unstop or any listed platform.

## 🛠️ Troubleshooting

| Problem | Fix |
|---|---|
| No message arrives | Confirm you messaged the bot first, and that `TELEGRAM_CHAT_ID` is correct |
| Digest didn't send on schedule | GitHub cron can lag by several minutes, and scheduled workflows pause after 60 days of repo inactivity. Trigger a manual run to re-activate |
| A source returns nothing | The site's endpoint may have changed. Check the Actions logs, then update that source module |
| Gemini errors or rate limits | The tool falls back to rule-based extraction automatically |
| Same events resent | Check that the workflow can commit `hackathons.db` back to the repo (Settings → Actions → Workflow permissions → Read and write) |

## 📄 License

MIT. See [LICENSE](LICENSE).

---

Built to help B.Tech students in Hyderabad find opportunities before the deadline passes. 🚀
