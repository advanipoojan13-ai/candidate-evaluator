# SDE3 - LinkedIn Rubric

**Role:** SDE3 - Agentic AI Technical Lead  
**Purpose:** Score and rank pre-filtered LinkedIn profiles.  
**Maximum score:** 62 points.

## Objective

Score four capabilities using three components:

1. Evidence
2. Recency
3. Evidenced Duration

For every capability, the AI returns:

- Evidence Points: 0-4
- Recency Points: 0-3
- Evidenced Duration Points: 0-3

The application calculates weighted capability scores, the Final Score, and rank. The AI must **not calculate or return these mechanical fields**.

The application first normalises available experience dates and role durations. These calculated role durations are inputs and upper bounds, not automatic evidence of capability-specific use. The scoring request returns component judgments without Score Rationale. After component validation and Python score calculation, a separate request receives the fixed scores and permitted evidence to write Score Rationale. Explanation output cannot change scores.

Missing LinkedIn information receives zero where evidence is required, but must be described as **unverified** or **not stated**. Missing information is not proof that the candidate lacks the capability.

## 1. Global Scoring Rules

1. Use only explicit information from permitted LinkedIn fields.
2. Score Evidence, Recency, and Duration independently.
3. Use the strongest valid evidence source once. Do not stack repeated mentions.
4. One achievement may support multiple capabilities only when it explicitly demonstrates each capability.
5. Score only based on written evidence.
6. Do not add undocumented bonuses, penalties, pass scores, or rejection rules.
7. In Score Rationale, provide a subjective, evidence-based explanation for all four capability scores in this order: Shipped AI Agent / Agent-Chatbot Delivery, FastAPI / Django, Backend / System Architecture, and AI Solution Breadth & Judgment.
8. For each capability, explain the candidate's relevant work, where the evidence appears, how the recency and supported duration affected the score, and what missing or unclear evidence prevented a higher score.
9. Do not treat a list of Evidence, Recency, or Duration point values as justification. Explain in natural language why the available evidence supports the resulting score.
10. End Score Rationale with a brief overall conclusion explaining the main reasons for the candidate's Final Score.

## 2. Fields to Use

### Allowed scoring fields

- Headline
- About section
- Experience title / position
- Experience description
- Experience-level skills or technologies attached to a specific role
- Experience start date
- Experience end date
- Current-status indicator
- Written role duration
- Project name
- Project description
- Project technologies

### Identification only

- Candidate name
- LinkedIn profile URL
- Current company
- Current title

Duplicate experience records must be merged before scoring.

## 3. Capabilities and Maximum Scores

Each capability receives a raw score out of 10:

> **Raw Capability Score = Evidence + Recency + Evidenced Duration**

| Capability | Multiplier | Maximum |
|---|---:|---:|
| Shipped AI Agent / Agent-Chatbot Delivery | x2.0 | 20 |
| FastAPI / Django | x1.8 | 18 |
| Backend / System Architecture | x1.4 | 14 |
| AI Solution Breadth & Judgment | x1.0 | 10 |
| **Total** |  | **62** |

The order and weights reflect the confirmed priority: shipped AI agent/chatbot work first, FastAPI or Django second, backend/system architecture third, and AI solution breadth and judgment fourth.

## 4. Evidence Points - Maximum 4 per Capability

Select exactly one Evidence score for each capability using the strongest valid source.

| Strongest supported evidence | Points |
|---|---:|
| Experience description explicitly shows the candidate personally built, implemented, designed, led, maintained, debugged, or delivered the capability | **4** |
| Role-specific technology/capability stack inside an experience, capability-specific experience title, or detailed serious deployed project explicitly identifies the capability | **3** |
| About section or Headline explicitly names the technology or capability | **2** |
| Experience-level skill/technology attached to a role, or an undetailed project, explicitly names the capability | **1** |
| No permitted evidence | **0** |

### Evidence rules

- Do not add Evidence Points from multiple sources.
- An experience title can receive 3 Evidence Points only when it specifically names the technology or capability. A generic engineering, leadership, or seniority title does not qualify.
- A project is deployed only when the profile explicitly describes release, deployment, users, sustained use, a live system, operation, or another concrete delivery context.
- A repository, tutorial, hackathon, demo, prototype, or POC alone does not prove shipment.

## 5. Recency Points - Maximum 3 per Capability

For each capability independently, find the most recent dated experience containing valid evidence.

| Most recent qualifying use | Points |
|---|---:|
| Current or ended within the last 12 months | **3** |
| Ended 13-36 months ago | **2** |
| Ended 37-60 months ago | **1** |
| Ended more than 60 months ago | **0** |
| Evidence is undated | **0** |

Recency may come from a capability-specific experience title, actual-use experience description, role-specific stack/list, or experience-level skill/tag. Headline, About, and undated Projects receive zero Recency Points.

## 6. Evidenced Duration Points - Maximum 3 per Capability

Duration measures how long dated professional experience supports the capability.

| Supported non-overlapping duration | Points |
|---|---:|
| Three years or more | **3** |
| Two years to under three years | **2** |
| One year to under two years | **1** |
| More than zero but under one year, or duration cannot be reliably established | **0** |
| None | **0** |

### Duration-source caps

- Experience description showing actual use or a capability-specific experience title: maximum 3
- Role-specific stack/list: maximum 2
- Experience-level skill/tag: maximum 1
- Headline, About, generic title, or undated Project: 0

### Duration rules

1. Use the full role duration only when the capability is described as an ongoing responsibility or sustained use.
2. A one-time achievement such as launched, designed, migrated, implemented, or set up does not receive the full role duration unless a time period or continuing responsibility is explicit.
3. Combine qualifying non-overlapping periods across roles.
4. Count overlapping time once per capability.
5. A serious deployed side project receives zero Duration Points unless its time period is explicitly available.

## 7. Approved Capability Evidence

### 7.1 Shipped AI Agent / Agent-Chatbot Delivery - Maximum 20

#### Count

- AI agent or agentic workflow
- LLM-powered agent or chatbot
- Tool-using AI agent
- Multi-agent system
- RAG/retrieval system used within an agent or LLM application
- LLM orchestration system
- Text-to-SQL system using an LLM
- Closely related applied GenAI system with clear delivery evidence

Frameworks such as LangGraph, LangChain, LlamaIndex, AutoGen, CrewAI, Semantic Kernel, or equivalents count only when connected to qualifying work.

#### Do not count as shipped delivery by itself

- Generic AI, ML, NLP, or data-science work
- Using ChatGPT, Copilot, Claude, or another AI assistant
- POC, prototype, demo, tutorial, coursework, or certification

#### Category-specific Evidence Points

| Strongest AI-agent evidence | Points |
|---|---:|
| Experience description explicitly confirms that the candidate built and shipped, deployed, released, operated, or delivered an AI agent, agentic workflow, or LLM-powered agent/chatbot | **4** |
| Experience description confirms qualifying agent implementation but shipment is unclear; or a role-specific agent stack, agent-specific experience title, or detailed serious deployed project identifies the capability | **3** |
| About section or Headline explicitly names qualifying AI-agent or agent-chatbot work | **2** |
| Experience-level skill/tag, framework keyword, or undetailed project contains only a qualifying term | **1** |
| No permitted evidence | **0** |

Use this category-specific table instead of the general Evidence table when scoring AI Agent / Agent-Chatbot Delivery.

Set **Shipped AI Agent / Agent-Chatbot Unverified = Yes** unless a permitted source explicitly confirms shipment or deployment. A serious deployed side project can resolve the warning.

### 7.2 FastAPI / Django - Maximum 18

Score explicit FastAPI or Django evidence. Either framework qualifies. Evidence of both frameworks does not increase Evidence Points beyond the strongest supported source.

#### Count

- FastAPI
- Django
- Django REST Framework / DRF
- Clear descriptions of building, maintaining, reviewing, debugging, or delivering services using these frameworks

#### Rules

- Award zero FastAPI / Django points for Flask, Python, or a generic Python-framework reference when neither FastAPI nor Django/DRF is explicit.
- A framework keyword in a stack or tag is valid but weaker than described engineering use.

Set **FastAPI / Django Unverified = Yes** when neither framework appears in a permitted source.

### 7.3 Backend / System Architecture - Maximum 14

#### Count

- Backend, platform, or end-to-end system architecture
- Service boundaries or monolith-versus-microservices decisions
- APIs and integrations as system-design work
- Messaging, queues, event-driven, or asynchronous architecture
- Scalability, reliability, availability, security, performance, or maintainability decisions
- Retrieval, orchestration, backend, or data architecture for AI systems
- Explicit technical trade-offs or technology-selection decisions

Kafka and SQS are illustrative examples only. Award architecture points for any explicitly evidenced messaging, queue, or asynchronous-design work under the same scoring rules.

Set **Backend / System Architecture Unverified = Yes** when no permitted source explicitly supports system-design, architecture, or technical trade-off responsibility.

### 7.4 AI Solution Breadth & Judgment - Maximum 10

#### Count

- RAG or retrieval choices
- Text-to-SQL
- Agent or multi-agent architecture
- Tool use and orchestration
- Memory or state management
- Prompt design or versioning
- Evaluation, guardrails, observability, quality measurement, or failure analysis
- Model/approach selection
- Accuracy, latency, cost, reliability, or maintainability trade-offs

The candidate need not have deployed every approach. Informed exploration can count when the profile explicitly demonstrates understanding. A list of tools or concepts without use or judgment is weak evidence.

## 8. Date Normalisation

1. Use stated month/year dates when available.
2. For Present roles, use the evaluation date as the end date.
3. A clear written duration may be used when dates are incomplete.
4. If only years are available:
   - Same start and end year: assign six months.
   - Later end year: estimate `12 x (end year - start year - 1) + 8 months`.
5. Do not create false month-level precision.
6. Count overlapping qualifying time once per capability.
7. For contradictory, impossible, or future-dated records, use only supportable duration and set **Date-Quality Warning = Yes**.

## 9. Calculation

For each capability, Python calculates:

> **Weighted Capability Score = (Evidence + Recency + Duration) x multiplier**

Python calculates:

> **Final Score = sum of all four weighted capability scores**

Maximum: **62**.

Use full precision internally. Display scores to one decimal place when necessary. Do not apply undocumented adjustments.

## 10. Non-Scoring Warnings

Return `Yes` or `No` for:

1. **Shipped AI Agent / Agent-Chatbot Unverified**
2. **FastAPI / Django Unverified**
3. **Backend / System Architecture Unverified**
4. **Date-Quality Warning**

Warnings do not alter scores. Always describe missing information as unverified or not stated.

## 11. Ranking

Rank candidates by Final Score from highest to lowest.

For equal scores, use:

1. Higher Shipped AI Agent / Agent-Chatbot Delivery score
2. Higher FastAPI / Django score
3. Higher Backend / System Architecture score
4. Higher AI Solution Breadth & Judgment score
5. Candidate name alphabetically

Tie-breakers affect rank only.

## 12. Final Output Schema

Export exactly these columns:

1. Rank Number
2. Candidate
3. Profile URL
4. Current Company
5. Current Title
6. Shipped AI Agent / Agent-Chatbot Delivery Score (/20)
7. FastAPI / Django Score (/18)
8. Backend / System Architecture Score (/14)
9. AI Solution Breadth & Judgment Score (/10)
10. Final Score (/62)
11. Shipped AI Agent / Agent-Chatbot Unverified
12. FastAPI / Django Unverified
13. Backend / System Architecture Unverified
14. Date-Quality Warning
15. Strongest Evidence
16. Missing or Unclear Information
17. Score Rationale

The AI also returns the 12 internal component-point fields used by Python. Component fields are not exported.

### Strongest Evidence

- Maximum three short points separated by ` | `.
- Identify the role/project and concrete fact.
- Prioritize shipped AI agent/chatbot work, FastAPI/Django, backend/system architecture, and AI solution breadth or judgment.
- Do not repeat the rationale.

### Missing or Unclear Information

State the most important uncertainties neutrally, especially shipment status, FastAPI/Django evidence, architecture, AI solution breadth or judgment, and dates.

### Score Rationale

Maximum **150 total words per candidate**, including all four capability explanations and the overall conclusion together. This is not a separate allowance for each capability. Aim for roughly 25–30 words per capability, then a brief overall conclusion. Use one concise narrative with clearly identifiable explanations for Shipped AI Agent / Agent-Chatbot Delivery, FastAPI / Django, Backend / System Architecture, and AI Solution Breadth & Judgment. Explain the relevant work and source, recency, supported duration, and the key missing or unclear evidence. Do not merely repeat component points or calculate the mechanical score fields. The application caps explanation text at 150 words without changing or rescoring validated numeric results; this also applies when saved results are displayed or exported.

## 13. Deterministic Edge Rules

- Repeated mentions do not increase Evidence Points.
- Multiple tools in one capability still produce one capability score.
- Generic AI/ML does not prove shipped AI agent/chatbot delivery.
- A generic chatbot does not prove an AI agent or LLM-powered chatbot.
- AI-assistant use does not prove applied-AI delivery.
- A POC/prototype does not prove shipment.
- A detailed deployed side project may satisfy shipped-agent evidence but gets no Recency or Duration unless dated.
- A named agent framework does not prove shipment or architecture depth.
- Award zero FastAPI / Django points for Python alone, Flask, or an unnamed Python framework.
- FastAPI or Django/DRF can qualify independently; evidence of both does not stack.
- Kafka and SQS are illustrative examples; other explicitly evidenced messaging or queue technologies qualify under the same rules.
- Title alone does not prove hands-on engineering, architecture responsibility, or applied AI judgment.
- Team outcomes do not automatically prove personal work.
- Do not score candidate experience length or generate a seniority warning.
- Missing evidence produces zero for the relevant component and an unverified warning where defined.
- Duplicate roles do not add repeated evidence or duration.
- Overlapping duration is counted once per capability.
