# Recording and presentation package

Use only passages supported by the running application. Replace bracketed cues. Synthetic records and demo payment/portal actions must remain visible on screen. Recordings below are scripts, not produced videos.

## Video: target 1:45–1:55

### 0:00–0:15 — Problem
Billing teams managing multiple locations have to connect scattered carrier bills with contracts and service records. AI Billing Rep is designed to investigate those bills and bring people the cases that need a decision.

[Show billing queue. Small label: synthetic demo.]

### 0:15–0:45 — Explained increase
This invoice rose from 450 to 525 dollars. A simple change alert would create work for the team. Here, the agent retrieves an approved amendment effective October first and checks the service period. The 75-dollar increase is supported. Change the period to September, and that same amendment no longer explains it.

[Show retrieved amendment, date, executed comparison. Say payment eligible only if policy checks run; label simulated queue.]

### 0:45–1:15 — Unexplained charge
This second account has a new 120-dollar adjustment. Our available records do not explain it, so the agent asks for clarification rather than declaring it wrong. The specialist reviews the evidence and approves this inquiry. [Show actual portal case confirmation only if working.] [Play at most five seconds of generated ElevenLabs audio; do not claim delivery.]

### 1:15–1:35 — Finance view
Finance sees the distinction immediately: a supported recurring increase, a charge still under review, and a 600-dollar promised credit that has not been counted as money recovered. Every result retains its source and assumptions.

### 1:35–1:55 — Implementation and evidence
[Show compact architecture.] Our implemented integrations are [verified list]. On [N] synthetic cases, the agent [actual result]. The repository includes the source records, expected outcomes, and limitations. We want to help billing teams finish investigations and give finance information they can inspect.

## Three-minute stage outline

- 0:00–0:25: User and pain; one historical audit example with date and source.
- 0:25–1:15: Supported increase, effective date, and September variation.
- 1:15–2:00: Unexplained adjustment, approval, confirmed inquiry.
- 2:00–2:25: CFO view and distinct financial states.
- 2:25–2:45: Actual integration architecture and measured test results.
- 2:45–3:00: Initial customer hypothesis and next pilot measurement.

Keep the routine backend waits in the video short; label cuts or time compression. For live stalls use a clearly labeled previously completed run, not a fabricated success message.

## Q&A answer notes

**Does this already exist?** Telecom expense-management vendors already automate invoices, audits, and disputes. Our prototype explores an investigation-first workflow with dated evidence and explicit handoff to finance. Faster deployment and better economics remain hypotheses to test.

**What if the model is wrong?** Show implemented source references, arithmetic checks, review states, and approval gates. Do not claim those controls exist if they are only planned.

**Did you pay a real bill?** No: the intended hackathon payment queue is simulated. Real payments need a payment integration and validated controls.

**Does the new surcharge prove overbilling?** No. It is unexplained from available evidence and needs clarification.

**How do you know a line is unused?** Invoice data alone cannot establish that. Usage and owner confirmation are needed; backup and alarm services may be essential despite low usage.

**What did you measure?** State case count, dataset limitations, actual correctness and runtime. Distinguish grader self-tests from agent runs.

**What does Arize learn?** It records traces and evaluations. Corrected facts are stored in the application/memory; evaluation cases test whether changes improve future behavior.

**What does Daytona add?** An isolated runtime for executable investigation. Sandbox isolation does not establish financial correctness; separate checks validate results.

**What is your first customer?** A distributed organization with multiple carriers and fragmented billing records. Name only genuinely contacted or committed customers, with permission.
