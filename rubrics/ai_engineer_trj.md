# LinkedIn Scoring Rubric --- Senior AI & Automation Engineer

## Purpose

Score and rank pre-filtered LinkedIn profiles for the Senior AI &
Automation Engineer role. Maximum score: **100**.

Score only what is evidenced on LinkedIn. Missing information means
**not evidenced**, not that the candidate lacks the capability.

## 1. Scoring Model

For each capability:

**Raw Score = Evidence + Recency + Evidenced Duration**\
Maximum raw score = **10**.

  Capability                          Multiplier       Max
  --------------------------------- ------------ ---------
  AI / LLM / Agentic Systems                ×3.0        30
  Python                                    ×2.5        25
  API & System Integration                  ×2.0        20
  Workflow Automation                       ×1.5        15
  TypeScript / Node.js                      ×0.5         5
  Ownership / Production Maturity           ×0.5         5
  **Total**                                        **100**

## 2. Evidence Sources

**May score:** Headline, About, experience title, experience
description, skills/technologies attached to a specific experience,
experience dates/duration, Projects.

**Identification only:** Name, profile URL, current company/title,
location, employment type.

**Do not score:** Global Skills/Top Skills, education, certifications,
courses, recommendations, endorsements, followers/connections,
languages, volunteering, company reputation, industry, recruiter-search
match, LinkedIn-inferred skills, or outside knowledge.

Do not infer capability from company, title, education, industry, or
another capability.

## 3. Capability Definitions

### AI / LLM / Agentic Systems --- 30

Evidence of building or implementing GenAI/LLM applications, RAG, AI
agents, agentic workflows, LLM orchestration, or tool-using AI systems.

Frameworks such as LangChain, LlamaIndex, AutoGen, CrewAI, or LangGraph
count only when connected to qualifying work.

**Rules** - Using ChatGPT/Copilot/Claude as a productivity tool does not
count. - Tool/framework lists without what was built are weak evidence
only. - Do not infer depth merely from "RAG", "agent", "chatbot", or
"LLM". - POCs/prototypes count as capability evidence but do not prove
production maturity. - Generic AI/ML without GenAI/LLM/RAG/agentic work
gets at most **1 Evidence Point** and no Recency/Duration unless dated
professional experience contains qualifying work.

### Python --- 25

Professional Python application/backend development,
scripting/automation, AI/LLM systems, APIs, integrations, or data
workflows. Django, Flask, and FastAPI count as Python evidence.

### API & System Integration --- 20

Building/integrating APIs, webhooks, third-party/SaaS systems,
databases, data pipelines, CRM/messaging/business systems, or other
system-to-system integrations. A software-engineering title alone does
not prove this.

### Workflow Automation --- 15

Business/operational workflows built with n8n, Make, Zapier, Pipedream,
custom Python/Node, or equivalent.

May include CRM, lead/customer, communication, document/data-processing,
support, internal-operations, or multi-system workflows.

Do **not** count QA/test automation, CI/CD, infrastructure automation,
browser testing, industrial/manufacturing automation, or tool names
without an identifiable business workflow.

### TypeScript / Node.js --- 5

Professional TypeScript or Node.js backend/application development.
Plain JavaScript or frontend-only work does not by itself qualify.

### Ownership / Production Maturity --- 5

Evidence of architecture/solution design, end-to-end delivery,
production deployment/operation, monitoring, reliability, scalability,
maintenance/optimization, or production cost/LLM-usage optimization.

"Built", "developed", or "worked on" alone does not prove production
maturity. Do not infer ownership from
Senior/Lead/Staff/Principal/Architect titles.

## 4. Evidence Points --- Max 4

Use the **strongest valid source only**; do not stack sources.

  Strongest evidence                                         Points
  -------------------------------------------------------- --------
  Experience description showing actual professional use          4
  Role-specific capability/technology stack                       3
  Capability-specific experience title                            3
  Headline clearly showing capability                             3
  About clearly showing capability                                2
  Skill attached to a specific experience                         1
  Project clearly showing capability                              1
  None                                                            0

Actual use means concrete work such as building, developing,
integrating, deploying, architecting, maintaining, operating, or
optimizing.

Repeated mentions and multiple tools within one capability do not
increase points.

## 5. Recency --- Max 3

Use the most recent **dated professional experience containing
qualifying evidence**.

  Most recent qualifying use         Points
  -------------------------------- --------
  Current / ended ≤12 months ago          3
  Ended 13--36 months ago                 2
  Ended 37--60 months ago                 1
  Ended \>60 months ago                   0

Headline, About, and Projects receive **0 Recency Points**.

## 6. Evidenced Duration --- Max 3

  Supported professional duration     Points
  --------------------------------- --------
  ≥3 years                                 3
  2--\<3 years                             2
  1--\<2 years                             1
  \>0--\<1 year                          0.5
  None                                     0

**Source caps:** actual-use description/capability-specific title = 3;
role-specific stack = 2; experience-level skill = 1;
Headline/About/Projects = 0.

Across roles, combine only non-overlapping supported duration. Do not
double-count.

## 7. Date & Calculation Rules

-   Use stated profile dates; current roles end on the evaluation date.
-   Do not invent missing dates/months.
-   Contradictory/impossible dates → use only supportable evidence and
    set **Date-Quality Warning = Yes**.
-   Calculate each capability independently.
-   Capability Score = Raw Score × multiplier, capped at its maximum.
-   Final Score = sum of six capability scores; maximum **100**.
-   Use full precision; display one decimal when needed.
-   No undocumented bonuses or penalties.

## 8. Unverified Flags

Flags do **not** change the score.

-   **AI / LLM / Agentic Systems Unverified = Yes** if absent from every
    permitted source.
-   **Python Unverified = Yes** if absent from every permitted source.
-   **API & System Integration Unverified = Yes** if absent from every
    permitted source.
-   **Seniority Unverified = Yes** if permitted evidence shows no
    meaningful ownership, architecture/design responsibility, end-to-end
    delivery, production responsibility, technical decision-making, or
    comparable senior engineering scope. Title alone does not resolve
    this.
-   **Date-Quality Warning = Yes** for material date contradictions.

Always describe missing capability as **unverified**, not absent.

## 9. Evidence Confidence

-   **High:** Major scores are supported primarily by dated actual-use
    experience descriptions.
-   **Medium:** Some actual-use evidence exists, but important scoring
    relies on stacks, titles, About, or incomplete descriptions.
-   **Low:** Important scoring relies mainly on Headline, About,
    Projects, attached skills, generic stacks, or sparse descriptions.

Evidence Confidence measures confidence in the **LinkedIn evidence**,
not candidate quality.

## 10. Ranking

Rank by Final Score. Ties: AI/LLM → Python → API/Integration → Workflow
Automation → Ownership/Production → TypeScript/Node.js → candidate name
alphabetically.

## 11. Locked Evaluator Rules

1.  Score only permitted evidence.
2.  Do not infer one capability from another.
3.  Do not reward keyword repetition or number of tools/frameworks.
4.  Do not infer depth, seniority, ownership, or production maturity
    from title/company/industry.
5.  POC/prototype evidence does not automatically equal production
    evidence.
6.  Evidence, Recency, and Duration are separate.
7.  Headline/About/Projects receive no Recency or Duration.
8.  If a higher score requires an assumption, use the lower score.
9.  Do not double-count duration.
10. Do not add rules, bonuses, or penalties not written here.

## 12. Final Output --- Use Exactly

``` text
Rank Number: [Rank]
Candidate: [Name]
Profile URL: [URL]
Current Company: [Company]
Current Title: [Title]

AI / LLM / Agentic Systems Score: __/30
Python Score: __/25
API & System Integration Score: __/20
Workflow Automation Score: __/15
TypeScript / Node.js Score: __/5
Ownership / Production Maturity Score: __/5

Final Score: __/100

AI / LLM / Agentic Systems Unverified: Yes / No
Python Unverified: Yes / No
API & System Integration Unverified: Yes / No
Seniority Unverified: Yes / No
Date-Quality Warning: Yes / No

Evidence Confidence: High / Medium / Low

Strongest Evidence 1: [Evidence]
Strongest Evidence 2: [Evidence]
Strongest Evidence 3: [Evidence]

Missing or Unclear Information: [Neutral statement]

Score Rationale: [50–75 words max]
```

### Output Rules

-   Strongest Evidence: maximum 3; prioritize higher-weight capabilities
    and actual-use evidence. State concrete work, not keyword lists.
-   Missing/Unclear: mention only material gaps and phrase neutrally.
-   Score Rationale: explain strongest evidence, main reason for the
    score, and most important uncertainty; do not repeat every subscore.
