# Hackathon Alert Automation

Finds new hackathons in Hyderabad twice a day and sends a digest to Telegram. Runs free on GitHub Actions.

## What it does

At **7:30 AM IST** and **6:30 PM IST**, the automation:

1. Collects hackathons from Unstop and other trusted platforms
2. Uses Gemini to extract details like venue, accommodation, team size, and eligibility
3. Ranks them for B.Tech students
4. Sends only **new** hackathons to Telegram (nothing is sent if there are no new ones)

## Digest contents

The digest has two sections:

- **Hyderabad Hackathons:** offline and hybrid events across Hyderabad
- **High-Popularity Picks:** events with big prizes, reputed organizers, or internship/PPO perks

Each hackathon shows:

- Title and host
- Venue and mode (offline / hybrid / online)
- Event dates
- Time left to apply
- Entry fee
- Team or solo
- Accommodation
- Prizes and perks
- Eligibility
- Registration link

Events closing within 48 hours are tagged **Closing soon** and re-sent once as a last call.

## Setup

### 1. Create the Telegram bot

1. Message [@BotFather](https://t.me/BotFather) on Telegram and send `/newbot`
2. Display name: `Hackathon Alert Automation`
3. Username: `HackathonAlert_bot`
4. Copy the bot token

### 2. Get your chat ID

1. Send any message to your bot
2. Open `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`
3. Copy the number under `"chat": {"id": ...}`

### 3. Get a Gemini API key

Create a free key at [Google AI Studio](https://aistudio.google.com/).

### 4. Configure GitHub

1. Go to **Settings → Secrets and variables → Actions** and add:

   | Secret | Value |
   |---|---|
   | `TELEGRAM_BOT_TOKEN` | Token from BotFather |
   | `TELEGRAM_CHAT_ID` | Your chat ID |
   | `GEMINI_API_KEY` | Your Gemini key |

2. Go to **Settings → Actions → General → Workflow permissions** and select **Read and write permissions**
3. Open the **Actions** tab, enable workflows, and run the workflow once manually to confirm the first digest arrives

After that it runs automatically twice a day.

## Run locally

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

## Configuration

Edit `config.yaml` to change:

- Which sources are enabled
- Which areas count as Hyderabad
- How many events appear per section
- Ranking weights
- The list of reputed organizers
- Which notifiers are enabled

## How ranking works

Events are scored in this priority order:

1. B.Tech eligibility
2. Final-year friendly
3. Free entry
4. Internship / PPO opportunity
5. Reputed organizer
6. Prize pool
7. Deadline urgency
8. Accommodation provided

## Email add-on

Email delivery is built in but disabled. To enable it:

1. Create a Gmail [App Password](https://support.google.com/accounts/answer/185833)
2. Add the secrets `SMTP_USER`, `SMTP_APP_PASSWORD`, and `EMAIL_TO`
3. Set `notifiers.email.enabled: true` in `config.yaml`

## Project structure

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
