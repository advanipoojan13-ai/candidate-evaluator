# LinkedIn Scoring Rubric - SafeGold Customer Support & Operations Executive (UAE)

**Role:** Customer Support & Operations Executive - SafeGold, Dubai, UAE

**Purpose:** Score and rank pre-filtered LinkedIn profiles.

**Maximum score:** 53 points.

## Objective

Score six capabilities using three components:

1. Evidence
2. Recency
3. Evidenced Duration

For C1-C5 and for each qualifying support channel, the AI returns:

- Evidence Points: 0-4
- Recency Points: 0-3
- Evidenced Duration Points: 0-3

The application selects the support medium, derives the final C6 components, and calculates weighted capability scores, the Final Score, and rank. The AI must not return these mechanical fields.

Missing LinkedIn information receives zero where evidence is required, but must be described as **unverified** or **not stated**. Missing information is not proof that the candidate lacks the capability.

---

# 1. Global Scoring Rules

1. Use only explicit information from permitted LinkedIn fields.
2. Do not infer capability from title, seniority, company name, employer reputation, education, or industry.
3. Do not infer that the candidate personally performed work merely because their team or employer performed it.
4. Score Evidence, Recency, and Duration independently.
5. Use the strongest valid evidence source once. Do not stack repeated mentions.
6. One achievement may support multiple capabilities only when it explicitly demonstrates each capability.
7. Do not reward keyword repetition or long lists of tools.
8. If a higher score requires an assumption, use the lower supported score.
9. Warnings do not change the score.
10. Do not add undocumented bonuses, penalties, pass scores, or rejection rules.
11. Candidate experience length and seniority are outside this rubric because the supplied profiles are already pre-filtered for suitable experience.

---

# 2. Fields to Use

## Allowed scoring fields

- Headline
- About section
- Experience title / position
- Experience description
- Experience-level skills or tools attached to a specific role
- Experience start date
- Experience end date
- Current-status indicator
- Written role duration
- Project name
- Project description
- Project tools

## Identification only

- Candidate name
- LinkedIn profile URL
- Current company
- Current title

Duplicate experience records must be merged before scoring.

---

# 3. Capabilities and Maximum Scores

Each capability receives a raw score out of 10:

> **Raw Capability Score = Evidence + Recency + Evidenced Duration**

| Capability | Multiplier | Maximum |
|---|---:|---:|
| Frontline Customer Support | x1.0 | 10 |
| Issue Resolution, Complaints & Escalations | x1.2 | 12 |
| KYC, AML/CFT, Disputes & Fraud | x0.8 | 8 |
| Partner Support, Case Records & Support Tools | x0.8 | 8 |
| Recurring Issues, Feedback & Support Content | x0.5 | 5 |
| Customer Support Medium | x1.00 / x0.80 / x0.60 / x0.40 / x0.20 (see Section 7.6) | 10 |
| **Total** |  | **53** |

Issue resolution carries the most weight. Frontline support and support medium each contribute up to 10 points.

---

# 4. Evidence Points - Maximum 4 per Capability

Select exactly one Evidence score for each capability using the strongest valid source.

| Strongest supported evidence | Points |
|---|---:|
| Experience description explicitly shows the candidate personally performed qualifying work in the capability | **4** |
| About section or Headline explicitly names the tool or capability | **3** |
| Role-specific tool/capability list inside an experience, capability-specific experience title, or detailed project delivered to real users explicitly identifies the capability | **2** |
| Experience-level skill/tool attached to a role, or an undetailed project, explicitly names the capability | **1** |
| No permitted evidence | **0** |

## Evidence rules

- Do not add Evidence Points from multiple sources.
- An experience title can receive 2 Evidence Points only when it specifically names the tool or capability. A generic executive, operations, leadership, or seniority title does not qualify.
- Headline and About provide Evidence Points only. They cannot by themselves establish hands-on support work, case ownership, compliance decisions, or customer outcomes.
- A detailed project delivered to real customers or partners can provide strong evidence, but an undated project receives no Recency or Duration.
- A project counts as delivered only when the profile explicitly describes use by real customers, partners, or a customer support team.
- A simulation, coursework exercise, draft, or demo alone does not establish delivery.

---

# 5. Recency Points - Maximum 3 per Capability

For each capability independently, find the most recent dated experience containing valid evidence.

| Most recent qualifying use | Points |
|---|---:|
| Current or ended within the last 12 months | **3** |
| Ended 13-36 months ago | **2** |
| Ended 37-60 months ago | **1** |
| Ended more than 60 months ago | **0** |
| Evidence is undated | **0** |

Recency may come from a capability-specific experience title, actual-use experience description, role-specific tool/capability list, or experience-level skill/tag. Headline, About, and undated Projects receive zero Recency Points.

Do not use the candidate's latest job date unless that job contains evidence of the capability being scored.

---

# 6. Evidenced Duration Points - Maximum 3 per Capability

Duration measures how long dated professional experience supports the capability.

| Supported non-overlapping duration | Points |
|---|---:|
| Three years or more | **3** |
| Two years to under three years | **2** |
| One year to under two years | **1** |
| More than zero but under one year, or duration cannot be reliably established | **0** |
| None | **0** |

## Duration-source caps

- Experience description showing actual use or a capability-specific experience title: maximum 3
- Role-specific tool/capability list: maximum 2
- Experience-level skill/tag: maximum 1
- Headline, About, generic title, or undated Project: 0

## Duration rules

1. Use the full role duration only when the capability is described as an ongoing responsibility or sustained use.
2. A one-time achievement such as closing a specific case, launching a process, or writing an FAQ does not receive the full role duration unless a time period or continuing responsibility is explicit.
3. Combine qualifying non-overlapping periods across roles.
4. Count overlapping time once per capability.
5. A serious project delivered to real users receives zero Duration Points unless its time period is explicitly available.

---

# 7. Approved Capability Evidence

Use the shared Evidence, Recency, and Evidenced Duration rules in Sections 4–6 for every capability. The lists below determine which work qualifies.

## 7.1 Frontline Customer Support - Maximum 10

### Count

- Answering external customers' questions about using a product or service, accessing an account, checking a transaction or order status, or understanding a service policy. Example “Answered customers' questions about withdrawal status and account access.”
- Guiding external customers through a service step, such as resetting access or submitting documents.
- An explicitly frontline support title such as Customer Support Executive, Customer Service Representative, or Customer Care Agent. A named channel is optional here. Evaluate channel priority in Section 7.6.

### Do not count

- Outbound sales, lead generation, or relationship management with no stated customer service duty.
- Internal employee help-desk work, social media publishing, or back-office data processing with no customer contact.
- “Contact Centre Agent,” “Executive,” or “Operations Associate” without a stated customer service function. A channel name or “omnichannel” alone does not establish that function.

Set **Frontline Customer Support Unverified = Yes** unless an Experience description explicitly confirms direct frontline work or a detailed project confirms the candidate personally supported real customers.

## 7.2 Issue Resolution, Complaints & Escalations - Maximum 12

### Count

- Investigating, troubleshooting, or resolving a specific type of customer problem, such as a failed payment, delayed withdrawal, blocked account, incorrect charge, or missing refund.
- Taking action on an escalation by coordinating a fix, providing case-specific progress updates, or confirming resolution. Example “Investigated delayed withdrawals, coordinated the fix, and confirmed resolution with customers.”
- A specific complaints, resolution, or escalations title or role responsibility, such as Customer Escalations Specialist. Report investigation, resolution, or closure only when the corresponding action is stated.

### Do not count

- Answering routine questions, processing a standard refund without investigating a problem, or posting a general service update.
- Logging, forwarding, or transferring a complaint without stated investigation, follow-up, or ownership. Case logging can qualify under Section 7.4.
- A generic Customer Support title, a standalone complaint-volume figure, or a claim such as “strong problem-solving skills” with no qualifying work.

Set **Issue Resolution, Complaints & Escalations Unverified = Yes** when no permitted description explicitly supports the candidate personally investigating, resolving, or managing a customer issue or escalation.

## 7.3 KYC, AML/CFT, Disputes & Fraud - Maximum 8

### Count

- Collecting identity or address documents explicitly for Know Your Customer (KYC) checks, checking those documents against KYC requirements, or recording a KYC decision the candidate was authorised to make.
- Performing or reviewing anti-money laundering or counter-terrorist financing (AML/CFT) checks, such as screening a customer or reviewing a flagged transaction.
- Gathering case details for, investigating, or processing a financial transaction dispute or chargeback. Identifying or escalating suspected fraud also qualifies when the fraud casework is explicit.
- Any one qualifying workstream. Report exactly what the candidate did and record a UAE regulatory connection only when stated.

### Do not count

- Generic onboarding, collecting contact details, profile edits, routine refunds, or unspecified “compliance” without a link to a qualifying workstream.
- Training, coursework, or certification alone as professional casework.
- Document collection as proof of verification or approval. Routing a fraud report does not establish that the candidate investigated or decided the case.

## 7.4 Partner Support, Case Records & Support Tools - Maximum 8

### Count

- Answering a distribution partner's question about a customer's account, case, or transaction, or resolving that issue for the partner.
- Creating, categorising, updating, or closing customer support tickets, recording complaint outcomes, or documenting a case handoff. Example “Updated Zendesk tickets with case notes and resolution status.”
- Freshdesk, Zendesk, or another CRM or ticketing tool when the permitted source explicitly ties it to customer support cases.

### Do not count

- Partner sales, commercial relationship management, or account planning with no customer or transaction support.
- A bare CRM keyword, CRM administration, sales pipeline updates, or generic data entry with no customer support case context.
- Case logging alone as issue investigation or resolution. Use Section 7.2 only when the candidate also performed a qualifying action under that criterion.

## 7.5 Recurring Issues, Feedback & Support Content - Maximum 5

### Count

- Tracking repeated incidents of a named issue or identifying a cause. Example “Tracked recurring wallet login failures and shared the findings with Product.”
- Sending Product, Operations, or another responsible team a specific customer complaint pattern or actionable feedback, or implementing a fix for a recurring support issue.
- Writing, updating, or translating a customer support FAQ, help article, call script, or response template. Record Arabic translation only when the language is named.

### Do not count

- Resolving one ticket, sending routine case replies, or passing on feedback without a specific issue or actionable detail.
- Generic “process improvement,” “feedback,” or “content creation” without a named support issue or support resource.
- Marketing copy or social posts created for promotion. Support content translated into Arabic does not establish native or spoken proficiency.

---

## 7.6 Customer Support Medium - Maximum 10

### Count

| Priority | Medium | Qualifying examples | Multiplier | Maximum |
|---:|---|---|---:|---:|
| 1 | Calls + Chat | Customer support over phone and via live chat, in-app chat, or WhatsApp. Both channels must be explicit. | x1.00 | 10 |
| 2 | Calls | Customer support over phone, inbound service calls, or outbound service callbacks | x0.80 | 8 |
| 3 | Chat | Live chat, in-app chat, or WhatsApp used for customer support | x0.60 | 6 |
| 4 | Email | Responding to customer queries or cases by email | x0.40 | 4 |
| 5 | Social Media | Responding to customer queries or complaints through social platform comments or direct messages | x0.20 | 2 |

### Do not count

- A bare channel name, “omnichannel,” “inbound,” “voice,” or “contact centre” without explicit customer support use. A phone number or email address on the profile is contact information.
- Sales calls, marketing emails, internal team chat, or social media publishing without customer service work.

### Rules

1. Select the first qualifying row in the table. Calls and Chat can be evidenced in the same role or in different roles. If both qualify, select **Calls + Chat** even if other channels also qualify.
2. For **Calls + Chat**, apply Sections 4–6 to each channel independently. The application uses the lower of the two channel scores for each component.
3. For an individual channel, apply Sections 4–6 using evidence and dates for that channel only. If Calls and Email qualify, select **Calls**. If Chat and Email qualify, select **Chat**.
4. Return separate components for Calls, Chat, Email, and Social Media in the response schema. Use null for a channel with no qualifying evidence. The application uses the exact label and multiplier of the first qualifying row. If no row qualifies, the application leaves the label blank and assigns zero to all components.

---

# 8. Date Normalisation

1. Use stated month/year dates when available.
2. For Present roles, use the evaluation date as the end date.
3. A clear written duration may be used when dates are incomplete.
4. If only years are available:
   - Same start and end year: assign six months.
   - Later end year: estimate `12 x (end year - start year - 1) + 8 months`.
5. Do not create false month-level precision.
6. Count overlapping qualifying time once per capability.
7. For contradictory, impossible, or future-dated records, use only supportable duration and set **Date-Quality Warning = Yes**.

---

# 9. Calculation

For each capability, Python calculates:

> **Weighted Capability Score = (Evidence + Recency + Duration) x multiplier**

For Customer Support Medium, use the multiplier for the selected label in Section 7.6. If the selected label is blank, the criterion scores zero.

Python calculates:

> **Final Score = sum of all six weighted capability scores**

Maximum: **53**.

Use full precision internally. Display scores to one decimal place when necessary. Do not apply undocumented adjustments.

---

# 10. Non-Scoring Warnings

Return `Yes` or `No` for:

1. **Frontline Customer Support Unverified**
2. **Issue Resolution, Complaints & Escalations Unverified**
3. **Date-Quality Warning**

Warnings do not alter scores. Always describe missing information as unverified or not stated.

---

# 11. Ranking

Rank candidates by Final Score from highest to lowest.

For equal scores, use:

1. Higher Frontline Customer Support score
2. Higher Issue Resolution, Complaints & Escalations score
3. Higher KYC, AML/CFT, Disputes & Fraud score
4. Higher Partner Support, Case Records & Support Tools score
5. Higher Recurring Issues, Feedback & Support Content score
6. Higher Customer Support Medium score
7. Candidate name alphabetically

Tie-breakers affect rank only.

---

# 12. Final Output Schema

Export exactly these columns:

1. Rank Number
2. Candidate
3. Profile URL
4. Current Company
5. Current Title
6. Frontline Customer Support Score (/10)
7. Issue Resolution, Complaints & Escalations Score (/12)
8. KYC, AML/CFT, Disputes & Fraud Score (/8)
9. Partner Support, Case Records & Support Tools Score (/8)
10. Recurring Issues, Feedback & Support Content Score (/5)
11. Customer Support Medium Score (/10)
12. Final Score (/53)
13. Selected Customer Support Medium
14. Frontline Customer Support Unverified
15. Issue Resolution, Complaints & Escalations Unverified
16. Date-Quality Warning
17. Strongest Evidence
18. Missing or Unclear Information
19. Score Rationale

The evaluation stores 18 internal component-point fields, including the three C6 components derived by Python from the channel evidence. Component points are not exported.

## Strongest Evidence

- Maximum three short points separated by ` | `.
- Identify the role/project and concrete fact.
- Prioritize frontline support and named channels, complaint or escalation actions, and relevant KYC, dispute, or fraud casework.
- Do not repeat the rationale.

## Missing or Unclear Information

State the most important uncertainties neutrally, especially the support medium when none is named, escalation ownership, and dates. Flag native Arabic and fluent spoken and written English as unverified if the permitted profile text does not state the required proficiency. Do not infer language proficiency from the candidate’s name or location.

## Score Rationale

Maximum 50 words. Explain the strongest supported capabilities and most important uncertainty without repeating every score.

---

# 13. Deterministic Edge Rules

- Repeated mentions do not increase Evidence Points.
- Multiple tools or workstreams within a capability still produce one score. For Customer Support Medium, score only the first qualifying row in Section 7.6.
- A generic Customer Support title does not prove a channel, issue resolution, or regulatory casework.
- Standard refunds do not prove payment dispute, fraud, or AML/CFT experience.
- Collecting KYC documents does not prove that the candidate approved or verified the documents.
- A CRM tool name alone does not prove hands-on case management.
- Social media publishing does not prove customer support through social media.
- A simulation or draft support project does not prove support of real customers. A detailed real-user project earns no Recency or Duration unless dated.
- Title alone does not prove hands-on support activity or resolution ownership.
- Team outcomes do not automatically prove personal work.
- Do not score candidate experience length or generate a seniority warning.
- Missing evidence produces zero for the relevant component and an unverified warning where defined.
- Duplicate roles do not add repeated evidence or duration.
- Overlapping duration is counted once per capability.
