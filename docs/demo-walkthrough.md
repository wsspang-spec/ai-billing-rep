# Demo walkthrough (about 2 minutes)

The question that drives the demo: **"Two bills went up. Which one should the billing team act on?"**

## Before you start (once)
1. Open the app and sign in: `maria@atlas.example` / `demo-password` (already filled in).
2. Click **Reset demo** (top right), then OK. The inbox is now empty.

## The demo
1. **Sign-in screen.** Say: "Maria pays the telecom bills for a company with offices in three cities." Click **Sign in**. (Users and sessions live in SurrealDB; the password is checked with its argon2 function.)
2. **Inbox is empty.** Click **Fetch from inbox (2)**. Each bill shows a live strip: Bill in → Claude reads → SurrealDB recalls → Daytona checks → Claude decides → Routed. Say: "The agent reads each PDF, looks up what we agreed to pay as of that date, and compares." Optional: drag in a third bill ("Get a sample bill" link) to show it live; a non-PDF is rejected with a message.
3. **Two results.** H-OCT-202 shows **Needs clarification**, N-OCT-101 shows **Explained**. Cards: 1 needs you, 1 explained, $525 scheduled.
4. **Open N-OCT-101 (Explained).** Point at:
   - "+$75.00, and it was expected."
   - **Price over time:** $450 until Sep 30 (Contract A), **$525 from Oct 1** (Amendment A), with "▲ this bill (October)" under the $525. Click **Amendment A ↗** to show the document.
   - Say: "The memory is time-aware. Because this bill is for October, the October price applies. The same $525 on a September bill gets held for review."
   - Payment card: $525 on Oct 27, **simulated**.
5. **Back to Inbox, open H-OCT-202 (Needs clarification).** Point at:
   - "$120.00 that nothing explains." Line 2, *Interstate Service Adjustment*, is highlighted.
   - **Why:** the contract sets $500 and says nothing about this adjustment.
   - **The agent proposes:** schedule the undisputed $500, keep $120 under review (not a saving), and ask the vendor. The question it drafted is shown.
6. **Show the guardrail.** Click **Try sending without approval** → red "Blocked (HTTP 403)". Say: "The model can propose. Code decides what's allowed."
7. Click **Approve inquiry**, then **Send to the carrier portal**. Wait about 20 to 40 seconds (Anchor opens a cloud browser, signs in, fills the form).
8. **Confirmed.** The card shows portal case **DEMO-CASE-001** and the status becomes **Awaiting vendor response**. Click **View it ↗** to open Harbor's portal and show the case Anchor filed. Say: "It's only marked submitted because the portal confirmed the case."
9. **Finance tab.** Billed $1,145; payments scheduled: $500 (Harbor, undisputed part) and $525 (Northstar), simulated; price change +$75/month from Oct 1; open questions $120; $600 credit promised but **saved so far $0**. Say: "Finance sees what's paid, what's open, and what's actually saved."
10. **How it works tab:** the diagram draws itself in the order a bill moves; press **Replay** to run it again.
11. To replay: **Reset demo**.

## If something goes wrong
- A bill stays on *Checking* for more than a minute: refresh the page. If it shows an error, click **Reset demo** and **Fetch** again (reads are cached, so the second run is fast).
- Sending to the portal fails: the card says *Not submitted* with the reason. Nothing is marked submitted. Click **Send** again.
- On any bill, **How the agent got here** (bottom) lists each step and which service ran it. That log is the app's own, stored in SurrealDB; the same steps are traces in Arize (project ai-billing-rep).
- To hide **Reset demo** for the real demo: start the app with `HIDE_RESET=1`.

## Lines for Q&A
- **How is this different from Tangoe or Calero?** They're established in this category. Our prototype shows one workflow: dated evidence picks the right price for the right period, actions are gated by approval, and the result flows straight into finance.
- **What if the model is wrong?** Totals, dates, duplicates and the approval gate are code. If the model calls something explained when a line doesn't match the price in effect, the code overrides it to *Needs review*.
- **Did it really pay?** No. Payment scheduling is a simulated queue.
- **Real carrier portals?** We tested on our own synthetic portal. Real portals need the customer's credentials.
- **Results?** 8 of the team's 14 labeled cases pass on the real app; the two demo cases passed 3 of 3 repeats. Synthetic data.
