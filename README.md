<div align="center">

# ⚡ HACKATHON ALERT AUTOMATION

**New hackathons in Hyderabad. Delivered to your Telegram. Twice a day. Zero cost.**

![Status](https://img.shields.io/badge/STATUS-ONLINE-00F0FF?style=for-the-badge&labelColor=0A0A1F)
![Schedule](https://img.shields.io/badge/SCAN-07:30%20%7C%2018:30%20IST-8B5CF6?style=for-the-badge&labelColor=0A0A1F)
![Delivery](https://img.shields.io/badge/DELIVERY-TELEGRAM-00F0FF?style=for-the-badge&labelColor=0A0A1F)
![Cost](https://img.shields.io/badge/COST-%240-8B5CF6?style=for-the-badge&labelColor=0A0A1F)

</div>

---

## ◈ SYSTEM OVERVIEW

At **07:30 IST** and **18:30 IST**, the automation runs on its own:

| Stage | Action |
|:---:|:---|
| `01` **SCAN** | Collects hackathons from Unstop and other trusted platforms |
| `02` **ANALYZE** | Uses Gemini to extract venue, accommodation, team size, and eligibility |
| `03` **FILTER** | Keeps only events suited for B.Tech students |
| `04` **DELIVER** | Sends **new** hackathons to Telegram. Silent if there's nothing new |

---

## ◈ DIGEST DATA

Each digest has two sections:

- **`SECTOR A`** Hyderabad Hackathons: offline and hybrid events across the city
- **`SECTOR B`** High-Popularity Picks: big prizes, reputed organizers, internship/PPO perks

Every hackathon includes:

| | | |
|:---|:---|:---|
| 🏆 Title and host | 📍 Venue and mode | 📅 Event dates |
| ⏳ Time left to apply | 💰 Entry fee | 👥 Team or solo |
| 🏨 Accommodation | 🎁 Prizes and perks | 🎓 Eligibility |
| 🔗 Registration link | 🔥 Closing-soon alert | |

Events closing within 48 hours are tagged **Closing soon** and re-sent once as a last call.

---

## ◈ DEPLOYMENT

### `STEP 1` Create the Telegram bot

1. Message [@BotFather](https://t.me/BotFather) and send `/newbot`
2. Display name: `Hackathon Alert Automation`
3. Username: `HackathonAlert_bot`
4. Copy the bot token

### `STEP 2` Get your chat ID

1. Send any message to your bot
2. Open `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`
3. Copy the number under `"chat": {"id": ...}`

### `STEP 3` Get a Gemini API key

Create a free key at [Google AI Studio](https://aistudio.google.com/).

### `STEP 4` Configure GitHub

1. Go to **Settings → Secrets and variables → Actions** and add:

   | Secret | Value |
   |:---|:---|
   | `TELEGRAM_BOT_TOKEN` | Token from BotFather |
   | `TELEGRAM_CHAT_ID` | Your chat ID |
   | `GEMINI_API_KEY` | Your Gemini key |

2. Go to **Settings → Actions → General → Workflow permissions** and select **Read and write permissions**
3. Open the **Actions** tab, enable workflows, and run the workflow once manually to confirm the first digest arrives

From here it runs automatically, twice a day.

---

## ◈ LOCAL MODE

```bash
git clone https://github.com/<your-username>/hackathon-alert-automation.git
cd hackathon-alert-automation
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # fill in your keys
```

```bash
python main.py --dry-run         # print the digest, send nothing
python main.py                   # real run
python main.py --force-resend    # ignore dedup and resend everything
pytest                           # run tests
```

---

## ◈ CONFIGURATION

Edit `config.yaml` to change:

- Which sources are enabled
- Which areas count as Hyderabad
- How many events appear per section
- Ranking weights and the reputed-organizer list
- Which notifiers are enabled

---

## ◈ EMAIL ADD-ON [DISABLED BY DEFAULT]

Email delivery is built in but switched off. To enable it:

1. Create a Gmail [App Password](https://support.google.com/accounts/answer/185833)
2. Add the secrets `SMTP_USER`, `SMTP_APP_PASSWORD`, and `EMAIL_TO`
3. Set `notifiers.email.enabled: true` in `config.yaml`

---

## ◈ PROJECT STRUCTURE

```
hackathon-alert-automation/
├── main.py
├── config.yaml
├── sources/          # one module per platform
├── enrich.py         # Gemini extraction
├── models.py         # hackathon data schema
├── ranker.py
├── storage.py        # SQLite dedup and cache
├── formatters/
├── notifiers/
├── tests/
└── .github/workflows/digest.yml
```

---

<div align="center">

`HACKATHON ALERT AUTOMATION` · Built for B.Tech students in Hyderabad

</div>
