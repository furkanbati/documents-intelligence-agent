# Demo video: setup and shot script

A 2–2.5 minute screen recording for Upwork and the GitHub README. Everything in
it is made up: the companies, tax numbers, invoices and amounts.

The story: **an invoice arrives by email → clean ones are approved on their own
→ suspicious ones reach the approver on Telegram with the reason → anyone can
ask questions about invoices and contracts in plain language.**

---

## 1. One-time setup (about 45 minutes)

### 1.1 A separate Gmail account for the demo

Create a new Gmail account to act as the company's accounting inbox (for example
`xyzmarket.muhasebe.demo@gmail.com`). Do not use your own inbox:

- the Gmail workflow processes every unread email with an attachment, and
- your inbox would be visible in the video.

You will send the invoices to this address from your own email or phone.

### 1.2 Google Cloud OAuth client (Gmail and Sheets)

n8n runs on your machine, so it needs its own Google OAuth client. Sign in to
https://console.cloud.google.com with the **demo** account:

1. Create a project, for example `n8n-demo`.
2. *APIs & Services → Library*: enable **Gmail API**, **Google Sheets API** and
   **Google Drive API**.
3. *OAuth consent screen*: user type **External**, app name `n8n demo`, your
   email as support and developer contact. Under *Test users* add the demo
   Gmail address.
4. *Credentials → Create credentials → OAuth client ID*: type **Web
   application**, authorised redirect URI
   `http://localhost:5678/rest/oauth2-credential/callback`.
   Copy the client ID and secret.

An app in *Testing* mode issues tokens that expire after 7 days. If Gmail or
Sheets stops working later, open the credential in n8n and sign in again.

### 1.3 Credentials in n8n

Open http://localhost:5678, then *Overview → Create → Credential*:

1. **Gmail OAuth2 API**: paste the client ID and secret, click *Sign in with
   Google*, choose the demo account and allow access.
2. **Google Sheets OAuth2 API**: same client ID and secret, sign in the same way.

The names don't matter; the setup script finds them by type.

### 1.4 The Google Sheet

In the demo account's Google Drive, create a spreadsheet named
`XYZ Market – Faturalar`. Rename the first tab to **Faturalar** and put this
header row in row 1 (paste it into A1; it splits on tabs):

```
Kayıt	Fatura Tarihi	Firma	Vergi No	Fatura No	Ara Toplam	KDV	Toplam	Durum	Kaynak
```

Make the header bold and freeze row 1 (*View → Freeze → 1 row*); it reads
better on video. Copy the spreadsheet's URL.

### 1.5 Telegram bot

1. In Telegram, open **@BotFather**, send `/newbot`, name it `XYZ Fatura Onay`
   and pick a username. Copy the token.
2. Open your new bot and send it `/start`.
3. Open `https://api.telegram.org/bot<TOKEN>/getUpdates` in a browser and copy
   the number after `"chat":{"id":`.

Install **Telegram Desktop** and record it. The approve/reject links point to
`localhost`, so they open on this PC. To tap them on a phone, n8n has to be
reachable from the internet (a Cloudflare Tunnel or ngrok address in
`PUBLIC_URL`); not needed for the video.

### 1.6 Put it together

Add to `.env`:

```
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
GOOGLE_SHEET_URL=https://docs.google.com/spreadsheets/d/.../edit
```

Then run the setup again:

```powershell
powershell -ExecutionPolicy Bypass -File .\kurulum.ps1
```

It should print `açık` (on) for *Telegram'a gönder*, *Google Sheets'e yaz* and
*Telegram'a bildir*, and publish `GmailFatura00002`. If a line says `kapalı`
(off), the credential or the `.env` value for it is missing.

**Test once before recording:** run `demo\demo-hazirla.ps1`, email
`demo\faturalar\2-deniz-ambalaj-onay-gerekli.pdf` to the demo inbox, and wait
1–2 minutes. A Telegram message should arrive; tap *Onayla* and check that a
row appears in the sheet.

---

## 2. Before every take

1. Reset the data:
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\demo\demo-hazirla.ps1
   ```
   This clears earlier test records and chat history, cancels old approval
   links, makes ABC Gıda a known supplier and Deniz Ambalaj an unknown one,
   and adds six approved invoices from October–November 2026 for the assistant.
2. Delete the old rows in the sheet (keep the header).
3. Clear the bot chat in Telegram (*⋮ → Clear history*).
4. **Warm up the models** a few minutes before recording: email any demo invoice,
   ask the assistant one question, then run the reset again. Cold, the first
   invoice takes about 40 seconds and the first answer up to a minute; warm,
   an invoice takes 5–15 seconds.
5. Screen: 1920×1080, browser zoom 110–125 %, notifications off
   (*Windows → Focus*), only the windows below open.

**Windows to have open**

| Window | Where |
|---|---|
| Your own email (sender) | Browser profile 1, compose window ready with the PDF attached |
| n8n, workflow *01 Fatura işleme* | Browser profile 2, http://localhost:5678 |
| Google Sheet | Browser profile 2, second tab |
| Telegram Desktop | Bot chat open |
| Assistant chat | Browser profile 2, http://localhost:5678/webhook/fatura-asistani/chat (sign in first: user `muhasebe`, password `ASISTAN_SIFRE` in `.env`) |
| Invoice PDFs | `demo\faturalar\`, opened in Edge |

---

## 3. Shot script (≈ 2:20)

Narration is in English; the on-screen product is Turkish, which shows the
Turkish e-Fatura niche. Where the screen is Turkish, add an English caption.
Cut every wait in editing; never show a spinner for more than 2 seconds.

### 0:00 – 0:12 · Hook

**Screen:** the invoice PDF `1-abc-gida-otomatik-onay.pdf`, then the n8n canvas
of *01 Fatura işleme*.

> "Accounting teams spend hours typing supplier invoices into spreadsheets and
> chasing approvals. This n8n automation reads every invoice, checks it, and
> only asks a human when something looks wrong."

### 0:12 – 0:30 · How it works

**Screen:** slowly pan across the n8n canvas; hover the nodes as you name them.

> "An invoice arrives by email. A document AI service reads the supplier, tax
> number, invoice number and amounts — from a PDF, a photo, or a Turkish
> e-invoice. Then the workflow runs the checks an accountant would: are all
> fields there, does subtotal plus VAT equal the total, is the supplier on our
> approved list, have we seen this invoice before, and is it under the
> auto-approval limit."

### 0:30 – 1:00 · Scene 1: a clean invoice is approved automatically

**Screen:** send the email with `1-abc-gida-otomatik-onay.pdf` (subject
`Fatura ABC2026000318426`). Cut. n8n *Executions* shows the new run in green.
Cut to the sheet: the row appears (4.200 TL, `otomatik_onay`).

> "Here's an invoice from a known supplier, ABC Gıda, for 4,200 lira. I just
> email it in. A few seconds later every field has been read, every check
> passed, and it's in the sheet — approved, with nobody touching it."

**Caption on the row:** `Read from the PDF · all checks passed · auto-approved`

### 1:00 – 1:40 · Scene 2: an unknown supplier needs approval

**Screen:** send `2-deniz-ambalaj-onay-gerekli.pdf`. Cut to Telegram Desktop: the
message arrives. Zoom in on it. Click **✅ Onayla**; the browser shows
*Fatura #8 onaylandı ✅*. Cut to the sheet: the second row appears (`onaylandi`).

> "Now an invoice from a supplier we've never worked with. The amount is fine,
> but the supplier isn't on the approved list — so instead of booking it, the
> approver gets a Telegram message with the reason. One tap to approve, and it's
> recorded with who decided and when, then added to the sheet."

**Caption on the message:** `"Supplier not registered (tax no. 4567890123)" · Approve / Reject`

### 1:40 – 1:52 · Scene 3: over the limit (short)

**Screen:** send `3-abc-gida-limit-ustu.pdf`. Telegram message arrives:
*Toplam 18.840,00 TL, otomatik onay limitini (10.000,00 TL) aşıyor*. Don't
approve it.

> "A known supplier, but 18,840 lira — over the 10,000 limit. That one waits
> for a manager."

**Caption:** `Over the 10,000 TL auto-approval limit → waits for a manager`

### 1:52 – 2:30 · Scene 4: ask anything

**Screen:** the assistant chat page. Type each question; cut the wait; let the
answer sit on screen for 2–3 seconds.

> "And because everything is recorded, the team can just ask."

| Type this | Expected answer (from rehearsal) |
|---|---|
| `How much did we approve for ABC Gıda in November?` | 2 invoices, 10,800.00 TL, both approved automatically |
| `Which invoices are still waiting for approval, and why?` | ABC2026000318431, 18,840.00 TL, over the 10,000 TL limit |
| `According to our approval policy, who has to approve that one?` | Between 10,000 and 100,000 TL → the accounting manager |
| `What are the payment terms in our contract with ABC Gıda?` | 30 days; 2 % discount if paid within 10 days |

> "Numbers come straight from the invoice database — the AI can only run fixed,
> read-only queries, so it can't make figures up. Contract and policy answers
> come from the company's own documents, with the source. And it remembers the
> conversation: 'that one' is the invoice from the previous answer."

Answers take 12–60 seconds on a laptop CPU. Cut the wait; don't speed it up.

### 2:30 – 2:45 · Close

**Screen:** the README on GitHub, or a simple end card.

> "It runs on n8n with Docker, and can run fully on your own server with local
> AI models, so invoices never leave the company — or on OpenAI for speed. It
> plugs into Gmail, Telegram and Google Sheets, and can be adapted to Outlook,
> WhatsApp or your accounting software. If your team still types invoices by
> hand, let's talk."

**End card:** your name · `n8n · Document AI · RAG · Python` · Upwork profile link
· `github.com/furkanbati/documents-intelligence-agent`

---

## 4. Recording and editing

- **Record:** OBS Studio (free; *Display Capture*, 1080p, 30 fps) or the Windows
  Snipping Tool's *Record* mode for single windows.
- **Voice:** record narration separately after the screen capture; it is much
  easier to fit the script to the cuts. A phone earbud mic in a quiet room is
  enough.
- **Edit:** Clipchamp (built into Windows) or DaVinci Resolve. Cut all waits,
  add the captions above, zoom in on the Telegram message and the sheet rows.
- **Export:** 1080p MP4. Upload to YouTube as *Unlisted*, link it from the
  Upwork portfolio item and the README, and use a still of the Telegram
  approval message as the thumbnail.
- **Before publishing,** watch it once with the sound off: the captions alone
  should tell the story.

## 5. If something goes wrong

| Symptom | Check |
|---|---|
| No Telegram message | `kurulum.ps1` printed `kapalı` for *Telegram'a gönder*? Token and chat ID in `.env`? Did you send `/start` to the bot? |
| Email not picked up | Is *02 Gmail eki → fatura işleme* published? The email must be **unread** and have the PDF **attached**. Gmail is checked once a minute. |
| No row in the sheet | Tab named exactly `Faturalar`, header row present, *Google Sheets'e yaz* `açık`? |
| Approve link says the execution is finished | You ran `demo-hazirla.ps1` after the message arrived; it cancels open approvals. Send the invoice again. |
| Assistant answers in Turkish | Ask again in a new chat (reload the page); the language rule is strong but the model is small. |
| Errors in general | n8n → *Executions* shows the failing node; `fatura.hatalar` has every error. |
