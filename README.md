# Job Tracker

> Reading this on your Mac? Double-click **README.html** for an easier-to-read version.

A free job-search tracker for Mac. It keeps everything in one Excel file, reads job postings for you, ranks them, watches your favorite companies for new openings and updates application statuses from Gmail.

Job Tracker runs on your own Mac. Your jobs, emails and resume details stay on your computer. Nothing is sent to an AI company, and there is no account or subscription.

It's built for people who apply to a lot of jobs and are tired of copying titles, pay and locations into a spreadsheet by hand. You paste a job link, and it fills in the company, title, pay, location, perks, office days, posted date and deadline. It then gives the job a **Priority score (0–100)** based on location, pay, how well the job fits you and its perks.

## Table of Contents

- [What it does](#what-it-does)
- [Privacy](#privacy)
- [Requirements](#requirements)
- [Install](#install)
- [First things to set](#first-things-to-set)
- [Usage](#usage)
  - [Add Job](#add-job)
  - [Check Jobs (the job watcher)](#check-jobs-the-job-watcher)
  - [Check Email](#check-email)
  - [Rescore Jobs](#rescore-jobs)
- [The spreadsheet](#the-spreadsheet)
- [How the Priority score works](#how-the-priority-score-works)
- [Adding a company](#adding-a-company)
- [Starter packs](#starter-packs)
- [Supported job sites](#supported-job-sites)
- [Updating](#updating)
- [Troubleshooting](#troubleshooting)
- [Uninstall](#uninstall)
- [Contributing](#contributing)
- [License](#license)

## What it does

| Tool | What it's for |
|---|---|
| **Add Job** | Paste a job link and it reads the posting: company, title, pay, location, remote/hybrid/on-site, office days per week, perks (bonus, 401k match, equity, relocation, PTO…), posted date and deadline. It asks whether you've applied and saves the job with a Priority score. |
| **Check Jobs** | Watches the careers pages of companies you list and shows **new** postings that match your title keywords and locations. You pick which ones to add. |
| **Check Email** | Reads your Gmail (read-only) and updates each application's status: received, interview, rejection, offer. It suggests follow-ups and marks jobs as Ghosted after a set time. |
| **Rescore Jobs** | Re-rates every saved job after you change your settings (keywords, background, pay target…). |

The full text of every posting is saved in the **Postings** folder, so you still have it after the job site takes it down. That's handy for interview prep.

## Privacy

- **Everything stays on your Mac.** The tracker is an ordinary Excel file in your folder.
- **The AI is local.** The optional AI helper uses [Ollama](https://ollama.com), a free and open-source app, with the Qwen3 model. It runs on your computer, with no cloud AI and no API keys.
- **Gmail is read-only.** Check Email reads your inbox using a Google *app password*. The password is stored in your Mac's **Keychain**, not in a file. The tool never sends, deletes or changes emails.
- **Job sites see a normal visitor.** Check Jobs reads the same public job lists a visitor to the company's careers page sees, a few requests at a time.

## Requirements

- A **Mac** (Apple silicon or Intel) with a recent version of macOS
- **Microsoft Excel**, for opening the tracker
- About **3 GB of free space** for the optional AI model (about 6 GB for the larger model), plus about 200 MB for the app
- A **Gmail** account, only if you want Check Email
- An internet connection for setup and for reading job postings. The tracker file itself opens offline.

Python is installed automatically if your Mac doesn't have it (Setup will prompt you).

## Install

Setup takes about 20 minutes and is done once.

1. **Download.** On this GitHub page, click the green **Code** button, then **Download ZIP**. Unzip it.
2. **Move the folder** somewhere permanent, such as `Documents/Job Tracker`. Keep everything in that folder together.
3. **Run Setup the first time from Terminal.** macOS blocks double-clicking downloaded scripts until they've been run once.
   - Open **Terminal**: press Cmd+Space, type `Terminal`, press Enter.
   - Type `bash ` (with a space), drag **Setup.command** from your folder into the Terminal window, and press Enter.
   - After this first run, every `.command` file in the folder opens with a normal double-click.
4. **Setup walks you through three steps:**
   1. **Python libraries.** If macOS offers to install "command line developer tools", click **Install**, wait for it to finish, then run Setup again.
   2. **Gmail accounts** (optional, for Check Email). For each account:
      - Turn on [2-Step Verification](https://myaccount.google.com/signinoptions/twosv).
      - Create an [app password](https://myaccount.google.com/apppasswords) and paste it when Setup asks.
      - Make sure IMAP is on: Gmail → Settings → See all settings → Forwarding and POP/IMAP.
   3. **Free local AI** (optional, recommended). Download [Ollama](https://ollama.com/download), drag it to Applications, open it once, then run Setup again. Setup downloads the AI model (about 2.5 GB) and runs a quick speed test.

You can run Setup again any time, for example to add an email account or switch AI models. It skips anything that's already done.

## First things to set

Open **Job_Tracker.xlsx** and fill in the **yellow cells**. Most results depend on these.

**Settings tab:**

| Setting | Example |
|---|---|
| Home (city, state) and max commute | `Denver, CO`, 40 miles |
| Target and minimum total pay | 95000 / 75000 |
| Fit keywords: what you want to work on | `CAD, robotics, test, medical devices` |
| My background: 3–8 lines about your degree, experience, tools and what you want (and don't want) | Used by the AI to rate fit |
| My years of experience | 2 |
| Dealbreaker words in the job title | `Senior, Director` |
| Watch: title keywords, skip words and locations | For Check Jobs (see below) |

The rest of Settings (points per perk, office-day scores, weights) has sensible defaults you can change later.

**Areas tab.** It starts empty. List the metros you'd move to, from most to least preferred, each with a center city, a radius and extra points (e.g. `Boston metro | Boston, MA | 40 | 1`). A row with just a state code (e.g. `CO`) covers the whole state. Order matters: a job counts toward the first row it falls in.

**Watch: locations to include** starts as `Home, Area, Region, Remote, Elsewhere` (all of the US). Once your Home and Areas are set, remove `Elsewhere` to see only the places you'd consider.

**Watchlist tab.** It starts with five example companies from different fields, all paused (Active = No). Turn on the ones you want, delete the rest, and add your own: see [Adding a company](#adding-a-company) and [Starter packs](#starter-packs).

**Better AI fit scores:** in Settings, change **AI model** to `qwen3:8b` if your Mac has 16 GB of memory or more, then run Setup again. It's slower, but noticeably better at judging fit.

## Usage

Double-click any of these in your Job Tracker folder. If Excel has the tracker open, the tool asks you to save and close it first.

### Add Job

1. Copy a job link (from LinkedIn, a company site, Indeed and so on).
2. Double-click **Add Job**. It offers the link you just copied, so press Enter, or paste a different one.
3. Check what it found. Press **Enter** if it looks right, or type fixes, for example:
   `title=Mechanical Engineer   pay=80000-95000   location=Boston, MA   days=3   deadline=11/14`
4. Answer **Applied already? (y/n)**. If yes, it asks which resume version you sent.
5. The job is saved with its Priority score and a short fit note, and the posting is copied so you can paste it into your resume-tailoring tool.

**Notes:**
- **Some sites (Apple, Motional and others) build pages with code the tool can't read.** If the details look wrong, open the posting in your browser, select all and copy (Cmd+A, Cmd+C), then type `c` at the review prompt.
- **Pasting a link for a job you already have** offers `r` to re-read it, or `a` to mark it applied.

### Check Jobs (the job watcher)

Each row on the **Watchlist** tab is one company: its name and the link to its careers page or job board. Double-click **Check Jobs**:

- **s** = scan for new jobs (quick, no AI)
- **a** = add the jobs you marked **Add** on the **New Matches** tab (reads each one with the AI)
- **b** = both

A scan lists postings that are **new**, have one of your **title keywords**, contain none of your **skip words** or **senior-level words**, and are in a **location** you'd consider. Type the numbers of the ones you want to add, or review them later on the New Matches tab: set **Action = Add** to add one, or **Dismiss** to hide it.

**Watchlist columns:**

| Column | What it does |
|---|---|
| Careers link | The company's job board. See [Supported job sites](#supported-job-sites) |
| Extra title keywords | Added to your main keyword list for this company. Start with `only:` to use **only** these, e.g. `only: structural, civil, facade` |
| Active | `No` pauses the company |
| Priority | 1, 2, 3… Check Jobs asks which priority to scan (Enter = 1). Put huge or slow companies at 2 or 3 and scan them on other days |
| My notes | Your own notes, e.g. "HQ Philadelphia, big in Boston" |
| Where they post (auto) | Filled in each scan, e.g. "Boston metro 7 · Elsewhere 16" |
| Last checked / Last result | When it was scanned and what happened ("290 postings scanned, 3 new matches") |

**How far back it looks:**
- **A company's first scan:** for a small company (60 postings or fewer), every matching job that's still open; for a big company, the last 14 days.
- **Later scans:** the days since that company's last scan, plus 2, between 7 and 14.
- **No repeats:** a job is never listed twice, and never if it's already in your tracker.
- **Warnings:** Check Jobs warns you when a priority group hasn't been scanned in 10 days.
- **Settings:** all of these numbers are under **JOB WATCHER**.

**After the priority question,** it asks **"Just some areas this time?"**. Press Enter for all your locations, or type part of an area name to see only matches there (`boston`, `LA`). For several areas, separate them with commas: `NYC metro, New Jersey`.

**Tips:**
- **Big companies** (thousands of postings) work best with a few specific keywords: `only: mechanical, design engineer`.
- **Exact phrases:** quotes require the words together, in order. `"product engineer"` won't match "Product Deployment Engineer".
- **Grow your skip words** from what you dismiss, e.g. `electrical, software, sales, HVAC`.
- **Senior filter:** **Watch: senior-level title words** and **Watch: level words** are plain lists you can edit. At consulting firms, add `Associate` if it's a senior title there.

### Check Email

Double-click **Check Email**. It reads recent emails from the accounts you added in Setup and:
- **Matches each email to a job** in your tracker (or adds the job if it's a confirmation for one you didn't track).
- **Updates the Status:** Applied, Screening, Assessment, Interview, Offer, Rejected.
- **Suggests follow-ups** after 10 days without a reply, and marks **Ghosted** after 30 (both changeable in Settings).
- **Logs every change** on the **Activity Log** tab, and puts emails it isn't sure about on **Needs Review**, so you can check them and mark **Done? = Yes**.

**Phone tip:** email yourself a job link with "job" in the subject. The next Check Email adds it, or marks it applied if the subject also says "applied".

### Rescore Jobs

After changing your keywords, background, pay target or AI model, double-click **Rescore Jobs**. It re-rates every job on To Apply (or every job, if you choose) and shows each change. Jobs whose saved posting looks incomplete are listed so you can re-read them (Add Job → paste the link → `r`).

## The spreadsheet

| Tab | What's on it |
|---|---|
| **To Apply** | Jobs you haven't applied to, best Priority first. Jobs closing within 3 days get a boost. |
| **New Matches** | New postings from Check Jobs, waiting for you to Add or Dismiss. |
| **Applied** | Applications in progress; anything needing action is at the top. |
| **Closed** | Rejected, Ghosted, Withdrawn, Skipped and Declined. |
| **Needs Review / Activity Log** | From Check Email (see above). |
| **Watchlist** | Companies for Check Jobs. |
| **Settings / Areas** | Your preferences (see [First things to set](#first-things-to-set)). |

**Notes:**
- **Jobs move between tabs on their own.** Change a job's **Status** or **Applied?** cell and it moves on the next run.
- **Columns with a lighter header are formulas** (Priority, Days Since Posted, Days Left, Est. Total Comp, Perks), so don't type in them. Fix a detail cell instead, e.g. set 401k Match to 4%, and they update instantly.
- **The [+] above the far-right columns** opens the scoring details: each perk, the four scores, the sentence each perk came from, and the full description.
- **Backups:** the last 15 versions of the tracker are kept in `app/backups`.

## How the Priority score works

Priority (0–100) is a weighted average of four scores out of 10 each. The weights are on the Settings tab.

| Score | Based on |
|---|---|
| **Location** | Home (within your commute) scores highest, then your Areas in order, then your preferred states (Region), then elsewhere. Remote and hybrid scores depend on office days per week. |
| **Pay** | Estimated total comp (base + bonus + 401k match + sign-on spread over 2 years) compared with your minimum and target. Missing pay gets a neutral score. |
| **Fit** | The AI compares the job's duties and requirements with your background, combined with your fit keywords and the experience level the job asks for. |
| **Perks** | Points per perk found in the posting (equity, strong health, PTO, gym, WFH stipend…). |

Every perk the AI reports is checked against the posting's own words, and the sentence it came from is saved, so you can always see why.

## Adding a company

Most companies take under a minute to add:

1. Go to the company's careers page and copy its address, e.g. `https://careers.example.com`.
2. Paste it into a new **Watchlist** row (Company in column A, link in column B) and run **Check Jobs**.
3. Look at the row's **Last result**:
   - **"X postings scanned"**: it works.
   - **"Not supported"**: open any one of the company's jobs, click **Apply**, and copy the address of the page that opens. That's usually the company's real job board. Paste it into the row instead and run Check Jobs again.

**Links that work** usually contain one of these:

| In the link | Hiring system |
|---|---|
| `myworkdayjobs.com` or `myworkdaysite.com` | Workday |
| `greenhouse.io` | Greenhouse |
| `lever.co` | Lever |
| `ashbyhq.com` | Ashby |
| `smartrecruiters.com` | SmartRecruiters |
| `eightfold.ai`, or `/careers?pid=` on a company site | Eightfold |
| `icims.com` | iCIMS |
| `oraclecloud.com` or `/sites/CX_` | Oracle |
| `bamboohr.com`, `ats.rippling.com`, `breezy.hr`, `recruiting.paylocity.com` | BambooHR, Rippling, Breezy, Paylocity |

Company-branded sites built on SuccessFactors or Phenom are recognized from the page itself, so paste the careers page.

**Shorten the link:** for Workday, keep only the part up to the site name, e.g. `https://jj.wd5.myworkdayjobs.com/JJ`. For Greenhouse, Lever and Ashby, keep only the company's board, e.g. `https://job-boards.greenhouse.io/spacex`. A link to a single job works too.

**Still not supported?** Some companies use systems the watcher can't read (Taleo, Paycom, JazzHR, Dover, or fully custom sites like Amazon and IBM). Use the company's own job alert emails, and [request the site](#contributing) on GitHub.

## Starter packs

Ready-to-paste companies and keywords by field. Copy the rows you want into your **Watchlist** (Company in column A, link in column B), and use the suggested keywords in **Settings → Watch: title keywords** or as `only:` keywords on those rows. The same list is in **companies.csv** in this folder. Links were checked in October 2026; companies sometimes move their job boards, so if one stops working, use [Adding a company](#adding-a-company) to find the new link.


### Civil & structural

Suggested keywords: `structural, structures, civil, building, enclosure, facade, façade, forensic, geotechnical, bridge, transportation`

| Company | Careers link |
|---|---|
| Thornton Tomasetti | https://careers.thorntontomasetti.com/us/en/search-results |
| WSP | https://emit.fa.ca3.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_2001/jobs |
| Arup | https://jobs.arup.com/jobs/search/22120486 |
| Stantec | https://hdhl.fa.us6.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1/jobs |
| AECOM | https://careers.smartrecruiters.com/AECOM2 |


### Mechanical, robotics & automation

Suggested keywords: `mechanical, mechatronics, robotics, electromechanical, design engineer, test engineer, controls engineer`

| Company | Careers link |
|---|---|
| Boston Dynamics | https://bostondynamics.wd1.myworkdayjobs.com/Boston_Dynamics |
| Agility Robotics | https://boards.greenhouse.io/agilityrobotics |
| Figure AI | https://job-boards.greenhouse.io/figureai |
| Skild AI | https://job-boards.greenhouse.io/skildai-careers |
| Intuitive | https://careers.smartrecruiters.com/Intuitive |
| Symbotic | https://symbotic.wd504.myworkdayjobs.com/Symbotic |
| Machina Labs | https://jobs.lever.co/MachinaLabs |


### Medical devices

Suggested keywords: `mechanical, R&D engineer, design engineer, product development engineer, test engineer, design quality`

| Company | Careers link |
|---|---|
| Medtronic | https://medtronic.wd1.myworkdayjobs.com/MedtronicCareers |
| Johnson & Johnson | https://jj.wd5.myworkdayjobs.com/JJ |
| Boston Scientific | https://bostonscientific.eightfold.ai/careers?domain=bostonscientific.com |
| Stryker | https://stryker.wd1.myworkdayjobs.com/StrykerCareers |
| Edwards Lifesciences | https://edwards.wd5.myworkdayjobs.com/EdwardsCareers |
| Insulet | https://insulet.wd5.myworkdayjobs.com/insuletcareers |
| Dexcom | https://dexcom.wd1.myworkdayjobs.com/Dexcom |
| ZOLL | https://zoll.wd5.myworkdayjobs.com/ZOLLMedicalCorp |


### Aerospace, space & defense

Suggested keywords: `mechanical, structures, propulsion, test engineer, integration engineer, design engineer`

| Company | Careers link |
|---|---|
| SpaceX | https://job-boards.greenhouse.io/spacex |
| Blue Origin | https://blueorigin.wd5.myworkdayjobs.com/BlueOrigin |
| Rocket Lab | https://job-boards.greenhouse.io/rocketlab |
| Sierra Space | https://sierraspace.wd1.myworkdayjobs.com/Sierra_Space_External_Career_Site |
| Anduril | https://job-boards.greenhouse.io/andurilindustries |
| Boeing | https://boeing.wd1.myworkdayjobs.com/EXTERNAL_CAREERS |
| NASA JPL | https://citjpl.wd5.myworkdayjobs.com/Jobs |


### Semiconductors & hardware

Suggested keywords: `mechanical, process engineer, equipment engineer, test engineer, hardware engineer, product engineer`

| Company | Careers link |
|---|---|
| KLA | https://kla.wd1.myworkdayjobs.com/Search |
| Microchip | https://wd5.myworkdaysite.com/en-US/recruiting/microchiphr/External |
| Apple | https://jobs.apple.com/en-us/search |
| Google | https://www.google.com/about/careers/applications/jobs/results/ |


### Analysis, test & data (hardware-adjacent)

Suggested keywords: `test engineer, validation engineer, reliability engineer, data analyst, systems engineer, analysis engineer`

| Company | Careers link |
|---|---|
| Draper | https://draper.wd5.myworkdayjobs.com/Draper_Careers |
| Philips | https://philips.wd3.myworkdayjobs.com/jobs-and-careers |
| Illumina | https://illumina.wd1.myworkdayjobs.com/illumina-careers |
| Stanley Black & Decker | https://sbdinc.wd1.myworkdayjobs.com/Stanley_Black_Decker_Career_Site |

## Supported job sites

**Add Job** reads most job links, including Greenhouse, Lever, Workday, Ashby, SmartRecruiters, Eightfold, LinkedIn and pages with standard job data. For anything else, use the copy-the-page method (`c`).

**Check Jobs** reads these hiring systems:
- Workday
- Greenhouse
- Lever
- Ashby
- SmartRecruiters
- Eightfold
- SuccessFactors
- Phenom
- iCIMS
- Oracle Recruiting
- Paylocity
- BambooHR
- Rippling
- Breezy HR
- Apple's and Google's careers sites
- Arup's job site (jobs.arup.com). Search there (for example, location: United States), and put the results link (`https://jobs.arup.com/jobs/search/<number>`) on the Watchlist. If Arup later shows "0 postings read", the saved search has expired, so search again and paste the new link.

Paste a company's careers page and it works out the system itself. If the Last result says **Not supported**, open one of that company's jobs, click **Apply**, and use the link of the page that opens. That's often the company's real job board. Companies on Taleo, Paycom, JazzHR or fully custom sites (e.g. Amazon, IBM) aren't supported; use their own job alerts.

## Updating

Updates never touch your tracker, Gmail logins, saved postings or AI model, and the old program files are backed up to `app/backups` first.

1. Close Excel.
2. Download the new version and unzip it.
3. Open the new folder and double-click **Install Update**. The first time, right-click it and choose Open. When it asks, drag your existing Job Tracker folder into the window.

The version number is shown at the top of Check Jobs, Add Job, Check Email and Rescore Jobs.

## Troubleshooting

| Problem | Fix |
|---|---|
| "cannot be opened because it is from an unidentified developer" | Right-click the file → **Open** → **Open**. Or run Setup once from Terminal (see [Install](#install)). |
| The tracker file disappeared from Finder | In Terminal: `chflags nohidden ~/Documents/"Job Tracker"/Job_Tracker.xlsx` (adjust the path to your folder). |
| "The tracker is open in Excel" | Save and close it (Cmd+S, then Cmd+W), then press Enter. |
| AI is off, or "took over 75 seconds" | Open the Ollama app once, run Setup again, or switch Settings → AI model to `qwen3:4b` (faster). Everything still works without AI, just less accurately. |
| Add Job saved the wrong title or company | Type fixes at the review prompt (`title=…`, `company=…`), or copy the posting page and type `c`. |
| Check Jobs: "sent a web page instead of job data" | The site was down or busy (e.g. a Workday outage). Try again in a few hours. |
| Check Jobs: "0 postings read… send the file app/debug/…" | The site's page format wasn't recognized. Open an issue on GitHub and attach that file. |
| Check Jobs finds very few jobs | Press Enter at "Just some areas this time?", check your title keywords and skip words, and remember a big company's first scan only looks back 14 days. |
| Check Email can't log in | Use an **app password** (not your normal password), and make sure IMAP is on in Gmail settings. |

## Uninstall

Delete the Job Tracker folder. If you installed Ollama and don't need it for anything else, drag it from Applications to the Trash and delete the `.ollama` folder in your home folder (press Cmd+Shift+. in Finder to show hidden folders). Gmail app passwords can be removed at [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords).

## Contributing

Questions, bugs and ideas are welcome. Please use **Issues** on this GitHub page. When reporting a problem, include:
- the message you saw (a screenshot of the Terminal window is fine),
- the version number shown at the top of the tool,
- for Check Jobs problems, the company's careers link and any file the message asked you to send.

**Request a job site:** if a company still says "Not supported" after trying its Apply-page link, open an Issue using the **Request a job site** template and fill in the company, its careers link and the Apply-page link.

**Suggest companies:** good companies and links for the [starter packs](#starter-packs) are welcome. Open an Issue, or edit **companies.csv**.

Please don't post your tracker file, emails or app passwords in an issue.

## License

[MIT](LICENSE) © Job Tracker contributors
