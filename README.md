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
  - [Review Jobs (the review screen)](#review-jobs-the-review-screen)
  - [Automatic daily scan](#automatic-daily-scan)
  - [Check Email](#check-email)
  - [Rescore Jobs](#rescore-jobs)
- [The spreadsheet](#the-spreadsheet)
- [The apply order](#the-apply-order)
- [Using a resume builder](#using-a-resume-builder)
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
| **Add Job** | Paste a job link and it reads the posting: company, title, pay, location, remote/hybrid/on-site, office days per week, perks (bonus, 401k match, equity, relocation, PTO…), posted date and deadline. It saves the job on **To Apply** with a Priority score. |
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
| My highest degree | `Bachelor's`, `Master's` or `PhD`. Used when a posting asks "BS + 5 years or MS + 3 years" |
| Dealbreaker words in the job title | `Senior, Director` |
| Watch: title keywords, skip words and locations | For Check Jobs (see below) |

The rest of Settings (points per perk, office-day scores, weights) has sensible defaults you can change later.

**Areas tab.** It starts empty. List the metros you'd move to, from most to least preferred, each with a center city, a radius, extra points and a **Tier** (1 = best; blank = 2), e.g. `Boston metro | Boston, MA | 40 | 1 | 2`. A row with just a state code (e.g. `CO`) covers the whole state. Order matters: a job counts toward the first row it falls in, so put a city above its state (`Denver metro` above `CO`). Home is always Tier 1, remote jobs Tier 3, anywhere else in the US Tier 4.

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
4. The job is saved with its Priority score and a short fit note, and the posting is copied so you can paste it into your resume-tailoring tool.

**Notes:**
- **Some sites (Apple, Motional and others) build pages with code the tool can't read.** If the details look wrong, open the posting in your browser, select all and copy (Cmd+A, Cmd+C), then type `c` at the review prompt.
- **Pasting a link for a job you already have** offers `r` to re-read it, or `a` to mark it applied.
- **When you apply,** set the job's **Status** to `Applied` (or **Applied?** to `Yes`) and it moves to the Applied tab on the next run. If you use a resume builder that writes `resume_log.csv`, it's done for you: see [Using a resume builder](#using-a-resume-builder).

### Check Jobs (the job watcher)

Each row on the **Watchlist** tab is one company: its name and the link to its careers page or job board. Double-click **Check Jobs**:

- **s** = scan for new jobs (quick, no AI)
- **a** = add the jobs you marked **Add** on the **New Matches** tab: no questions, a few seconds each, saved every 5 jobs
- **b** = both

A scan lists postings that are **new**, have one of your **title keywords**, contain none of your **skip words** or **senior-level words**, and are in a **location** you'd consider. Type the numbers of the ones you want to add, or review them later on the New Matches tab: set **Action = Add** to add one, or **Dismiss** to hide it.

**Requirement check.** After the scan, Check Jobs reads the full description of each possible match (only those, several companies at once) and fills in the **Pay**, **Requirements** and **Filtered** columns on New Matches:

- **Experience:** a posting whose *required* experience is **4 years or more** is filtered. Preferred lines and "Preferred" sections don't count, ranges use the low end (`3-5 years` = 3), and if the posting offers a shorter path for your degree (`BS + 5 or MS + 3`) that one is used.
- **Degree field:** a posting whose degree line names **only** fields that aren't yours (by default CS, computer engineering, EE, software, IT) is filtered. If it also accepts engineering, a field of yours, "a related field", or ends an open list with "etc.", it's kept and labeled, e.g. `CS/EE-leaning`.
- **Required skills:** phrases in **Watch: required-skill dealbreakers** (empty at first) filter a posting when they appear in a required line.
- **Local candidates only:** a posting that only hires people who already live nearby ("only considering candidates local to position location", "must live within commuting distance") is greyed, unless the job is in your Home area. The wording is on Settings: **Watch: local-candidates-only wording**. Postings that only say they won't pay for a move are not greyed; the Review screen tags them **no relocation help**.
- **Pay:** a posting that lists pay is filtered when the top of its range is below your **Minimum acceptable total pay** (hourly pay counts as × 2080). Postings without pay are never filtered for pay. Switch: **Watch: filter jobs whose top pay is below my minimum**.
- **Filtered jobs** are shown **greyed** below the real matches, with the reason and the posting's own words, once each. When you trust the filter, set **Watch: show filtered jobs on New Matches** to `No`: they're left off and listed in `app/debug/skipped.csv` instead.
- **Can't read a posting?** It's kept, marked `not checked`. Descriptions are remembered for 30 days, so re-scans are fast.
- **Add Job** runs the same check and prints a heads-up; it never blocks you.

All the lists are on Settings under **JOB WATCHER** (filter years, degree fields that count for you, fields that aren't, preferred-line words). Set the years to `0` to turn the experience filter off.

**Watchlist columns:**

| Column | What it does |
|---|---|
| Careers link | The company's job board. See [Supported job sites](#supported-job-sites) |
| Extra title keywords | Added to your main keyword list for this company. Start with `only:` to use **only** these, e.g. `only: structural, civil, facade` |
| Active | `No` pauses the company |
| Priority | 1–6. Check Jobs asks which priority to scan (Enter = 1). Put huge or slow companies at 2 or 3 and scan them on other days |
| Max Tier | 1–4: the farthest location tier you'd take **at this company** (see the Areas tab). Big companies with offices everywhere work well at `2`: jobs in other places are found but greyed. Blank = no limit |
| My notes | Your own notes, e.g. "HQ Philadelphia, big in Boston" |
| Where they post (auto) | Filled in each scan, e.g. "Boston metro 7 · Elsewhere 16" |
| Last checked / Last result | When it was scanned and what happened ("290 postings scanned, 3 new matches") |

**How far back it looks:**
- **A company's first scan:** for a small company (60 postings or fewer), every matching job that's still open; for a big company, the last 14 days.
- **Later scans:** the days since that company's last scan, plus 2, between 3 and 14.
- **No repeats:** a job is never listed twice, and never if it's already in your tracker.
- **A company that fails for a moment** (timeout, dropped connection) is tried once more at the end of the same scan. If it still fails, nothing is lost: its next scan looks back to its last successful one.
- **Warnings:** Check Jobs warns you when a priority group hasn't been scanned in 10 days.
- **Settings:** all of these numbers are under **JOB WATCHER**.

**Recheck (r).** Re-runs your current settings (title words, experience, degree, skills, pay) on the New Matches rows you haven't added or dismissed. Rows that now fail are greyed with the reason; rows that now pass are un-greyed. Use it after changing skip words or filter settings. Nothing is added, dismissed or removed.

**Deep scan (d).** Scans one company you name (even a paused one) for every open matching job, however old, instead of only recent ones. Use it after adding a big company, or to catch up on one. Jobs you've already been shown aren't repeated.

**Am I missing jobs?** Every scan writes `app/debug/titles.csv`: every posting it read and why it was or wasn't shown (`MATCH`, `no title keyword`, `skip word: CPU`, `senior: Senior`, `location: …`, `older than this scan's 14 days`, `filtered: …`). Open it in Excel and sort by **Result**. Titles marked `no title keyword` that you'd want tell you which keywords to add; a skip word that catches good jobs tells you which to remove. Each scan also keeps the one before as `titles-previous.csv`, so you can compare two scans. Workday, Apple and Google list every job posted in your scan window; other keyword-search sites (Eightfold and others) only list jobs that matched your keyword searches. If a site cuts a scan short ("asked to slow down"), Check Jobs lists that company at the end under **Partly checked**: run it again later.

**Adding the jobs you marked (a).** Each posting is read, scored and saved on To Apply without any questions (no AI, so it's quick; Rescore Jobs can use the AI later). If a posting doesn't list pay, the pay the scan read from the job list is used. At the end you get a summary: jobs added, jobs it couldn't read (usually taken down; they stay marked Add), and jobs without pay (also saved in `app/debug/no_pay.txt`).

**New Matches columns:**

| Column | What it means |
|---|---|
| Track | `Engineering` or `PM / Customer` (from **Track:** words on Settings) |
| Role Type | Rotational / Early Career, Project / Product Mgmt, Applications & Field, Quality & Reliability, Test & Validation, Manufacturing & Process, Controls & Robotics, Systems & Integration, Design / R&D, or Other (from the **Role type:** rows on Settings, checked top to bottom) |
| Tier | 1 = Home, an Areas row = its Tier, 3 = Region and remote, 4 = elsewhere in the US |
| Years | Years of experience the posting requires for your degree. Blank = not stated. Filter it, e.g. 0–2 plus blanks |
| Co. Priority | The company's Watchlist priority |
| Same Job, Other Links | The same job posted more than once (same title, place and description): the copies are folded into one row and their links listed here |

**Order:** jobs to decide (and ones marked Add) first, then greyed ones, then ones you've added or dismissed; within each group, newest posting first.

**Keeping the list fresh.** Once a week after a scan (or any time with **x**), Check Jobs checks whether your saved jobs and undecided New Matches are still posted. It counts pages that stay up but say the job is gone ("this job no longer exists", "applications are closed"), and it asks sites built with code (Apple, Google, Eightfold, Oracle) whether the posting still exists. A job is marked **Expired** only after it looks closed on two different days; Applied jobs are never touched. A passed **deadline** never closes a job (many stay open until filled): it adds a reminder in **Next Action** instead. Expired and Skipped jobs untouched for 60 days move out of the workbook into `app/archive.csv`.

**After the priority question,** it asks **"Just some areas this time?"**. Press Enter for all your locations, or type part of an area name to see only matches there (`boston`, `LA`). For several areas, separate them with commas: `NYC metro, New Jersey`.

**Tips:**
- **How big companies are searched:** on **Workday** sites, Check Jobs reads the company's whole board newest-first back to your scan window, so every recent matching title is found. Once a week it also runs all your keyword searches over the full 14 days, to catch the rare job a board lists out of date order (the other days skip them, which makes daily scans much faster). **Apple and Google** are read the same way. Other keyword-search sites (Eightfold, SuccessFactors, Phenom…) are searched with all your title keywords; Eightfold sites are read more slowly because they limit fast readers.
- **Big companies** (thousands of postings) work best with a few specific keywords: `only: mechanical, design engineer`.
- **Exact phrases:** quotes require the words together, in order. `"product engineer"` won't match "Product Deployment Engineer".
- **Grow your skip words** from what you dismiss, e.g. `software, sales, HVAC`. Phrases work too and are safer than single words: `electrical engineer, electrical design` skips those titles but keeps "Electrical/Mechanical Engineer" and "Electro-Mechanical Engineer".
- **Senior filter:** **Watch: senior-level title words** and **Watch: level words** are plain lists you can edit. At consulting firms, add `Associate` if it's a senior title there.
- **Titles that contain a skip word:** a skip or senior word doesn't count when it's part of a title keyword you listed. With the keyword `associate product manager`, "Associate Product Manager" gets through even though `Manager` is a skip word; "Senior Associate Product Manager" is still skipped.

### Review Jobs (the review screen)

Double-click **Review Jobs** (first time: in Terminal, type `bash `, drag **Review Jobs.command** in, press Enter). A page opens in your browser; it's served from your Mac only, nothing goes online. Keep the Terminal window open while you review.

- **To review** shows your undecided New Matches, 5 at a time, in the [apply order](#the-apply-order). Each job shows its company and group, title, years asked, Fit, pay, posted date, locations and tiers, requirements, the fit notes, and the full saved description (click **Description** or press **E**). The link is there too.
- **Watch-out words** (Settings) are highlighted on the job and in its description, e.g. thermal or CFD. They never hide a job.
- **The same job in several places** is one card listing each location; tick the ones you want and press Add (the others count as skipped).
- **Add (A)** adds the job exactly like Check Jobs > a. **Skip (S)** dismisses it; press a number for a reason (yours are on Settings > **Review: skip reasons**), **O** to type your own, or Enter for none. **Later (L)** moves it to the end for now.
- When you've decided on all 5, the next 5 load. Your decisions are recorded as you go and written to the workbook (and the jobs you added put on To Apply) when you press **Save to workbook** or **Done: save and close**, or close the Terminal window. If the tracker is open in Excel, close it first; anything not saved yet is saved the next time you open the screen.
- **Greyed** shows the jobs the scan filtered; **Skipped** shows what you skipped, with a **Bring back** button; **Settings** edits your company groups, fit threshold and watch-out words.
- **Every decision is kept** in `app/decisions.csv` (date, decision, reason and the job's details), so you can look back at what you add versus skip.

### Automatic daily scan

Let your Mac scan for you every morning. Open **Auto Scan** (first time: in Terminal, type `bash `, drag **Auto Scan.command** in, press Enter) and choose:

- **1 = turn on.** Every active Watchlist company is scanned once a day from 6:30 am. If Excel has the tracker open, or there's no internet yet, it tries again every hour until 9:30 pm. If the Mac was asleep at 6:30, it runs when the Mac wakes. On battery it waits until you're using the Mac (a closed laptop wakes briefly in the background now and then, and a scan started then would freeze halfway); plugged in, it runs any time. A notification tells you what it found ("7 new matches, 3 in Tier 1-2"); the jobs are on New Matches as usual.
- **3 = run now.** Start a scan in the background, e.g. to test it. If macOS asks whether Python may access your Desktop or Documents folder, click **Allow** (otherwise the scheduled scan can't open your tracker; see Troubleshooting).
- **4 = show the log** of the last scan (also in `app/debug/auto_scan.log`).
- **5 = wake the Mac at 6:25 am** (asks for your Mac password; works when it's plugged in with the lid open). Undo with `sudo pmset repeat cancel`.
- **2 = turn off.** Removes the schedule completely.

The automatic scan only finds and greys jobs. Adding them (a), recheck (r) and deep scans (d) stay in Check Jobs.

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
| **New Matches** | New postings from Check Jobs, waiting for you to Add or Dismiss. Greyed rows were filtered (reason in the Filtered column). |
| **Applied** | Applications in progress; anything needing action is at the top. |
| **Closed** | Rejected, Ghosted, Withdrawn, Skipped, Declined and Expired (posting taken down). |
| **Needs Review / Activity Log** | From Check Email (see above). |
| **Watchlist** | Companies for Check Jobs. |
| **Settings / Areas** | Your preferences (see [First things to set](#first-things-to-set)). |

**Notes:**
- **Jobs move between tabs on their own.** Change a job's **Status** or **Applied?** cell and it moves on the next run.
- **Columns with a lighter header are formulas** (Priority, Days Since Posted, Days Left, Est. Total Comp, Perks), so don't type in them. Fix a detail cell instead, e.g. set 401k Match to 4%, and they update instantly.
- **The [+] above the far-right columns** opens the scoring details: each perk, the four scores, the sentence each perk came from, and the full description.
- **Backups:** the last 15 versions of the tracker and the last 10 versions of the program files are kept in `app/backups`; older ones are deleted.
- **Company names** are tidied when a job is added: `1000 KLA Corporation` → `KLA`, and a job on a company's own job board gets your Watchlist name for it.

## The apply order

One rule decides what to look at and apply to first. It's used by the Review screen, New Matches, To Apply and jobs.csv.

- **Groups** (Settings, or the Review screen's Settings tab): **Apply: referral companies** and **Apply: top companies**, comma-separated. Every other company is Other. Names match like Co. Priority does, so a job filed under a company's legal name still counts.
- **Order:** jobs in Tier 1-2 first (Referral, then Top, then Other), then every other job in the same group order.
- **Within a group:** jobs whose **Fit** is below **Apply: fit threshold** (default 5) go last; then jobs asking 0-2 years, then "not stated", then more; then highest Fit; then newest posting.
- **Fit** is the same 0-10 score on New Matches and To Apply, from your Fit keywords and the years the job asks (the AI can refine it on To Apply with Rescore Jobs).

## Using a resume builder

The tracker and a separate resume tool can work together through two plain files, without ever editing the same file:

- **`jobs.csv`** (next to the workbook, rewritten on every run): every live job with its ID, company, title, Track, Role Type, location, tier, pay, status, link, the full description, its place in [the apply order](#the-apply-order) (**Apply Group**: Referral / Top / Other, and **Apply Rank**: 1 = apply first, blank once applied), and a **Requirements** summary such as `Years: 3+; Degree: BS Mechanical/Aerospace (or related); Skills: GD&T, Creo; Citizenship: US`. Read it by column name.
- **`resume_log.csv`** in a folder named **Resume Builder** next to your Job Tracker folder, written only by the resume tool. Columns: `Job ID, Resume Version, Base, File, Created, Submitted, Accomplishments`. On each run the tracker fills **Resume Version** on the matching job, and moves the job to **Applied** only when **Submitted** has a date (a resume being made is not an application). If a Job ID appears more than once, the newest row wins. The tracker never writes this file, and skips it if it isn't there.

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
3. Open **Terminal** (Applications > Utilities), type `bash ` (with a space), drag **Install Update.command** from the new folder into the Terminal window, and press Enter. (Double-clicking it usually fails with "Apple could not verify it is free of malware".) When it asks, drag your existing Job Tracker folder into the window.

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
| Automatic scan: "can't open your Job Tracker folder" | macOS blocked the background scan from your Desktop/Documents folder. System Settings → Privacy & Security → **Files and Folders** (or **Full Disk Access**) → allow **python3**, then Auto Scan → 3 to test. Or keep the Job Tracker folder somewhere outside Desktop/Documents/Downloads. |
| Automatic scan didn't run | Auto Scan → 4 shows the log. The Mac must be on (or asleep and able to wake), the tracker closed in Excel, and the internet connected. |

## Uninstall

If you turned on the automatic scan, open Auto Scan and choose **2** first. Then delete the Job Tracker folder. If you installed Ollama and don't need it for anything else, drag it from Applications to the Trash and delete the `.ollama` folder in your home folder (press Cmd+Shift+. in Finder to show hidden folders). Gmail app passwords can be removed at [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords).

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
