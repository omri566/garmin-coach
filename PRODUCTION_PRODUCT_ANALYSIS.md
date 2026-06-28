# Production Product Analysis: Garmin-Connected Endurance Coaching

Status: architectural and product recommendation  
Prepared: 2026-06-28  
Scope: a new consumer production repository, initially for iOS/App Store plus a web account portal  
Source prototype: this repository

## 1. Executive decision

Build a new production repository. Do not turn this repository directly into the production service.

The current repository is useful and should remain the personal product laboratory. It captures valuable domain behavior: Garmin ingestion, FIT parsing, endurance metrics, trend presentation, plan generation, and a coaching workflow. Its architecture is intentionally local, single-user, synchronous, and trusted. Those assumptions affect almost every module, so adding login screens and replacing SQLite would not make it production-safe.

The production product should be a multi-tenant cloud service with:

- A native iOS client for the App Store.
- A small web application for account, consent, privacy, subscription, and support flows. A full web dashboard can follow later.
- A versioned public API used by both clients.
- Official Garmin Connect Developer Program APIs and OAuth 2.0. The product must never collect or store a user's Garmin password.
- Server-authoritative entitlements for Free and Premium.
- Asynchronous, idempotent ingestion and analytics workers.
- Deterministic training and safety rules, with an LLM limited to explanation and bounded proposals.
- Explicit consent, tenant isolation, encryption, auditability, data export, disconnection, and deletion.

The primary feasibility gate is Garmin approval and confirmation that the official APIs expose every metric required by the product. Garmin states that its Connect Developer Program is for business use, uses OAuth 2.0, supports Activity, Health, and Training APIs, and requires approval. Its public pages do not promise every metric currently obtained by the prototype's unofficial consumer client. This must be resolved before committing to the premium feature set.

## 2. Product definition

### 2.1 Product promise

The product is not simply "Garmin Connect with different charts." Its defensible promise should be:

> Turn an athlete's Garmin history and current recovery signals into transparent, personalized endurance analysis and an athlete-approved training plan.

The differentiator is the closed loop:

1. Import activity and recovery data.
2. Explain changes in fitness, fatigue, technique, and execution.
3. Build a goal-specific plan within explicit constraints.
4. Match completed activities to planned sessions.
5. Propose plan changes with reasons and confidence.
6. Require the athlete to approve material changes.
7. Optionally publish approved workouts to Garmin.

This is meaningfully different from a generic dashboard and is narrow enough to build and test.

### 2.2 Initial target user

The first production audience should be adult recreational runners who:

- Already use Garmin Connect consistently.
- Run approximately three or more times per week.
- Have a race or performance goal.
- Want analysis and planning but do not have a human coach.
- Understand that the service is training guidance, not diagnosis or medical care.

Cycling can contribute cross-training load in version 1, but the plan engine should remain running-primary. Supporting every sport at launch would multiply session taxonomies, load models, safety rules, and device behavior without strengthening the initial product.

Start with adults only. A product processing minors' location and health-related data introduces additional consent, App Store, privacy, and safety work.

### 2.3 Naming and Garmin relationship

The commercial product should have an independent name and visual identity. Do not name it "Garmin Coach" or imply that it is a Garmin product. Use wording such as "Connect Garmin" or "Works with Garmin" only in the forms permitted by the applicable agreement and brand rules.

Garmin's public brand guidance requires attribution for Garmin device-sourced data. Brand and attribution requirements need to be part of design review, not added immediately before App Store submission.

## 3. What the current repository actually provides

The repository's `README.md`, `SPEC.md`, and `ARCHITECTURE.md` describe an ambitious single-user product. The implementation provides the following reusable product knowledge.

| Area | Current behavior | Production value |
|---|---|---|
| Garmin connection | `garminconnect`/`garth`, email and password or interactive prompt, MFA, local token cache | Proves the desired data and user flows; the authentication mechanism must be replaced |
| Activity ingest | Pulls activity summaries, downloads original FIT, parses records, writes FIT and Parquet | Good behavioral reference for source fidelity and idempotency |
| Health ingest | Pulls resting HR, HRV, sleep, Body Battery, stress, steps, readiness, and acute load | Defines desired recovery inputs; official API availability must be verified |
| Storage | Shared local SQLite plus filesystem FIT, Parquet, JSON plans, recommendations, profile, and knowledge files | Useful prototype schema; unsuitable for tenancy, concurrency, migrations, retention, or audit |
| Analytics | TRIMP, rTSS, HR zones, EF, decoupling, normalized power, technique averages, CTL/ATL/TSB, ACWR, volume and trend views | Candidate domain formulas, after scientific review and regression tests |
| Dashboard | Local Dash application with Overview, Deep Analysis, and Coach tabs | Strong interaction prototype and visual reference, not a mobile production client |
| Coaching | LLM-generated recommendations and a three-month/next-month plan | Validates product demand; the generation authority and evidence controls must change |
| Plan execution | Dated schedule, greedy activity matching, drag rescheduling, done/skipped overrides | Good starting vocabulary for a real plan/session/adherence domain model |
| Knowledge | LLM web research saved as a versioned JSON knowledge base | Demonstrates provenance need; autonomous citation collection is not sufficient for production |

### 3.1 Important gaps between the specification and implementation

The production plan must be based on implemented behavior, not the phase labels in the README. Several specified capabilities are partial or absent:

- Gap detection exists, but confidence flags and confidence bands are not consistently propagated through analytics, coach context, and UI.
- ACWR is displayed as a "sweet spot" and used as an injury-risk concept. The evidence does not support treating it as a causal injury-prevention threshold.
- Recovery is summarized for the LLM; there is no independently tested recovery state machine that reliably gates a plan.
- Plan adherence is primarily schedule matching and simple status handling, not the session-type execution scoring described in `SPEC.md`.
- Grade-adjusted pace, critical speed/power, full pace-duration curves, and robust race prediction are not implemented as production domain services.
- LLM output is extracted as JSON but is not comprehensively validated against the documented schemas or semantic safety rules.
- Knowledge-base citations are generated by an LLM and saved without a mandatory human verification workflow.
- The dashboard runs long sync and AI actions in the web process. There is no durable queue, retry policy, dead-letter handling, or job recovery.
- Dependencies are unpinned, schema changes are embedded in application startup, and test coverage is limited to a browser smoke tool rather than a regression suite.

These are not criticisms of a local prototype. They identify the work that a production product must make explicit.

## 4. The critical Garmin integration decision

### 4.1 Do not use the current login method in production

The prototype asks for a Garmin email/password, can prompt for MFA, and stores consumer session tokens locally. A commercial app should not ask users to provide Garmin credentials to the app's own form or server.

The production flow must be:

1. User creates or signs into the product account.
2. User taps **Connect Garmin**.
3. The app opens Garmin's authorization page using an external browser/authentication session.
4. Garmin authenticates the user and shows consent.
5. Garmin redirects to a registered universal link/callback.
6. The backend exchanges the authorization result, stores encrypted tokens, records consent, and starts a backfill job.

The UI should say "Connect your Garmin account," not "Enter your Garmin account details." The distinction is important: Garmin receives the credentials; this product receives authorization.

Garmin's Connect Developer Program FAQ states that all program APIs use OAuth 2.0 and that the program is for business use. The Activity API provides activity files, including FIT, after user consent. The Training API can publish workouts and plans to Garmin Connect after consent. See [Garmin's program overview](https://developer.garmin.com/gc-developer-program/), [program FAQ](https://developer.garmin.com/gc-developer-program/program-faq/), [Activity API](https://developer.garmin.com/gc-developer-program/activity-api/), and [Training API](https://developer.garmin.com/gc-developer-program/training-api/).

### 4.2 Obtain approval before freezing the product scope

Garmin approval is a product dependency, not a late integration task. Before creating the full implementation backlog:

- Form the business entity that will enter the developer agreement.
- Apply with a clear consumer coaching use case, estimated users, territories, requested APIs, data retention approach, and monetization model.
- Request Activity API, Health API, and Training API access.
- Obtain the private API documentation and legal terms.
- Confirm webhook/push delivery, backfill limits, quotas, deletion obligations, attribution, caching, derived-data rights, and sandbox/reviewer support.
- Confirm whether commercial use of desired Health metrics has license fees. Garmin's public Health API page says some commercial use requires a license fee.

Do not launch with the unofficial consumer API as a temporary production bridge. It creates credential, rate-limit, terms, operational, and App Review risk, and it would force a disruptive re-consent migration later.

### 4.3 Required metric compatibility audit

The public Garmin pages promise broad categories, not the complete field-level contract. Build a signed-off matrix from the private documentation and test payloads.

| Required input | Public confidence | Required decision |
|---|---|---|
| Activity summary and original FIT | High | Verify history depth, file availability, corrections/deletions, and push semantics |
| Activity HR, pace, cadence, GPS, running dynamics | Medium-high | Verify which fields survive in FIT for supported devices and how device attribution must appear |
| Sleep, heart rate, steps, stress, Body Battery | High | Verify delivery latency, corrections, licensing, and per-user consent granularity |
| HRV status and nightly HRV | Unclear from public material | Must be confirmed before recovery promises |
| Training readiness and acute load | Unclear | Must not be a launch promise until contractually and technically verified |
| VO2max, lactate threshold, race predictions | Unclear | Decide whether to ingest, calculate independently, or omit |
| Workout and training-plan publishing | High through Training API | Verify supported workout step taxonomy and device compatibility |

The system must expose source and quality for every metric: Garmin-provided, calculated, estimated, unavailable, stale, or low-confidence. Never silently substitute one source for another.

## 5. Identity, onboarding, and account model

### 5.1 Separate three identities

The production system has three different concepts that must not be conflated:

1. **Product account**: identifies the person in this service and owns data, plans, consent, and entitlements.
2. **Garmin connection**: an external authorization linked to the product account.
3. **App Store customer/subscription**: Apple purchase identity and transactions linked to the product account.

Use an immutable internal `user_id` as the join point. Do not use email, Garmin user ID, or Apple transaction ID as the primary application identity.

### 5.2 Recommended sign-in options

For iOS version 1:

- Sign in with Apple.
- Email magic link or passkey as the non-Apple recovery/portable option.
- No password stored by this product.
- No Google/social login unless there is a real acquisition need; every provider adds account-linking and support edge cases.

Use a managed OIDC identity provider under an appropriate data-processing agreement rather than building authentication primitives. Keep only authentication data in that provider; keep Garmin and health-related data in the product backend.

### 5.3 Onboarding sequence

Recommended sequence:

1. Product value and limitations in one screen.
2. Product account creation/sign-in.
3. Age confirmation and territory-specific terms/privacy acceptance.
4. Explicit explanation of Garmin data categories and why each is used.
5. Garmin OAuth consent.
6. Backfill choice and progress screen.
7. Profile review: units, HR zones, threshold, experience, training days, injury/medical limitation disclaimer, goal.
8. First useful free result as soon as a small recent window is processed.
9. Premium offer only after the user sees their data, unless a free trial is active.

Do not block initial UI on a full-history backfill. Process recent activities first, show partial/stale states clearly, and continue in the background.

### 5.4 Required account controls

Both the iOS app and web portal should provide:

- View Garmin connection and last successful sync.
- Reauthorize or disconnect Garmin.
- Pause syncing without deleting the account.
- Export data in a documented portable format.
- Delete imported activity/health data while retaining the product account, if legally and contractually supportable.
- Delete the entire account in-app.
- View and manage subscription status.
- View active sessions/devices and revoke them.
- View privacy notices and consent history.

Apple requires apps that support account creation to allow account deletion in the app. Apple also notes that deleting an app account does not itself cancel an App Store subscription, so the deletion flow must make that clear. See [Apple's account deletion guidance](https://developer.apple.com/support/offering-account-deletion-in-your-app).

## 6. Free and Premium product boundaries

Entitlements should represent user value and cost, not scattered UI flags. Data rights, consent, security, account deletion, and export are never premium features.

### 6.1 Recommended initial tiers

| Capability | Free | Premium |
|---|---|---|
| Product account and one Garmin connection | Yes | Yes |
| Automatic ongoing sync | Yes | Yes |
| Initial backfill | Recent window, proposed 90 days | Full available history, subject to Garmin limits |
| Last activity and activity list | Yes | Yes |
| Basic load/recovery snapshot | Yes | Yes |
| Basic volume, pace, and zone trends | Limited range | Full range and comparisons |
| Deep per-activity splits, drift, and technique | Preview or a small recent quota | Full |
| Goal definition | One simple goal | Full goal and availability model |
| Generated training plan | No | Yes |
| Adaptive weekly coach and recovery-aware proposals | No | Yes |
| Execution/adherence scoring | Summary only | Full session-specific analysis |
| Publish approved workouts to Garmin | No | Yes |
| Data quality/source explanations | Yes | Yes |
| Export, disconnect, consent controls, deletion | Yes | Yes |

This tiering gives Free a complete useful loop—connect, sync, understand current state—while Premium sells the expensive and differentiated coaching loop.

### 6.2 Premium usage policy

Do not promise unbounded AI generation. A sensible premium service caches daily analysis and limits expensive operations by product semantics, for example:

- A plan is revised when the athlete requests it or when a meaningful event occurs, not on every app open.
- Daily guidance is generated at most once per data state unless the user explicitly refreshes.
- Full plan regeneration has a transparent fair-use limit.
- Deterministic metrics remain available if the AI provider is degraded.

### 6.3 Downgrade behavior

A downgrade should change access, not unexpectedly destroy the user's history. Define and publish a policy before launch:

- Continue ingesting the Free-supported recent window.
- Preserve existing historical derived records for a documented period or while the account remains active.
- Consider deleting old raw FIT after a defined retention period while preserving minimal derived history, if permitted.
- Restore Premium views immediately on re-subscription if retained data is still available.
- Never treat subscription cancellation as withdrawal of health-data consent; they are different state transitions.

## 7. App Store subscription design

Premium unlocks digital functionality in the iOS app, so the default implementation should use Apple's In-App Purchase. Apple Guideline 3.1.1 says that feature/functionality unlocks in an app must use In-App Purchase. Multiplatform services may recognize a subscription bought on the web when the same capability is also available as an in-app purchase. Regional external-purchase rules are changing and operationally complex; they should not be the version 1 foundation. See the current [App Review Guidelines](https://developer.apple.com/app-store/review/guidelines/).

Recommended design:

- One auto-renewable subscription group.
- Monthly and annual Premium products.
- Optional introductory trial after unit economics are known.
- StoreKit 2 in iOS.
- Send an Apple `appAccountToken` tied to the internal user so purchases can be associated safely.
- Store a server-side entitlement ledger, not a single mutable `is_premium` boolean.
- Process App Store Server Notifications V2 for purchase, renewal, billing retry, grace period, refund, revocation, upgrade, downgrade, and expiration.
- Reconcile periodically against the App Store Server API in case a notification is delayed or missed.
- Let the app unlock promptly from a verified device transaction while the server converges.
- Provide restore purchases and manage subscription actions.

Apple recommends server notifications for maintaining current cross-platform state, and V1 notifications are deprecated. See [App Store Server Notifications](https://developer.apple.com/documentation/appstoreservernotifications) and the [App Store Server API](https://developer.apple.com/documentation/appstoreserverapi).

If web billing is added later, normalize Apple and web-billing records into the same entitlement ledger. The payment processor should receive identifiers and billing data, never activity or health metrics.

## 8. Recommended production architecture

### 8.1 Repository strategy

Create one production monorepo with independently deployable applications and shared contracts. A practical layout is:

- `apps/ios`: native SwiftUI application.
- `apps/web`: account, privacy, support, and later dashboard web application.
- `services/api`: authenticated product API and webhook endpoints.
- `services/worker`: ingestion, FIT parsing, analytics, plan, and notification jobs.
- `packages/domain`: pure, versioned analytics and coaching-domain logic.
- `packages/contracts`: API/event schemas generated for clients.
- `infra`: environment definitions, deployment policy, dashboards, and runbooks.
- `docs`: product specification, threat model, data map, domain glossary, ADRs, and operating procedures.

This is one product repository, but it does not force all components into one runtime or deployment.

Keep this local repository separate. Port behavior intentionally through specifications and tests. Do not copy local data, Garmin tokens, generated knowledge JSON, or personal profile values into any production environment.

### 8.2 Reference technology choices

These choices maximize reuse of the existing domain knowledge without carrying over the local architecture:

| Layer | Recommendation | Reason |
|---|---|---|
| iOS | Swift + SwiftUI | Native authentication, StoreKit, background behavior, accessibility, and App Store quality |
| Web | TypeScript web framework with server rendering | Strong account/support flows and shared generated API types |
| API | Python 3.13 + FastAPI or equivalent typed framework | Reuses Python analytics expertise and produces OpenAPI contracts |
| Worker | Python containers using the same domain package | FIT/parquet/scientific ecosystem and shared formula implementation |
| Primary database | Managed PostgreSQL | Transactions, migrations, concurrency, tenancy, audit records, and operational maturity |
| Object storage | Encrypted S3-compatible storage | Raw FIT, normalized stream files, export bundles, and large immutable artifacts |
| Queue | Managed durable queue with dead-letter support | Isolates Garmin/webhook/API latency from parsing and coaching work |
| Scheduler | Managed scheduler emitting queue jobs | Reconciliation, stale connection checks, subscription checks, cleanup |
| Secrets/keys | Managed secret store and KMS | Token and secret rotation, access audit, envelope encryption |
| Observability | Structured logs, metrics, traces, alerting, error reporting | Production diagnosis without exposing user health data |

Use a managed container platform initially. Kubernetes is unnecessary for the expected early scale and would add operational surface. Choose a cloud and region only after data-residency, Garmin agreement, LLM provider, and target-market review. On AWS, for example, the logical mapping could be managed containers, RDS PostgreSQL, S3, SQS, EventBridge Scheduler, KMS, and Secrets Manager; the architecture should not depend on AWS-specific semantics in the domain layer.

### 8.3 Service boundaries

Start as a modular monolith for the authenticated API plus one scalable worker deployment, not many microservices. Enforce boundaries in code and data ownership:

- **Identity and account**: users, sessions, account lifecycle.
- **Connections and consent**: Garmin authorization, scopes, revocation, sync state.
- **Ingestion**: external events, backfill, source assets, normalization, corrections.
- **Analytics**: versioned derived metrics, data quality, trend projections.
- **Coaching**: goals, plans, sessions, revisions, approvals, adherence, recommendations.
- **Entitlements**: products, transactions, access decisions.
- **Knowledge and model governance**: reviewed evidence, formula/model/prompt versions.
- **Privacy operations**: export, deletion, retention, legal holds, audit evidence.

Split deployments only when load, reliability, team ownership, or security boundaries justify it.

### 8.4 Request and data flow

The normal flow should be:

1. Garmin sends a notification, or a scheduled reconciliation finds new data.
2. The webhook validates authenticity, stores a deduplicated inbox event, and acknowledges quickly.
3. A job resolves the internal user and fetches only the authorized resource.
4. The original payload/file is stored immutably with checksum, source metadata, and retention class.
5. A parser writes normalized activity/health records and a compact stream artifact.
6. Analytics compute versioned derived metrics.
7. Read models for overview and activity analysis are refreshed.
8. A meaningful state change may enqueue a bounded coaching assessment.
9. The user sees freshness, source, and processing status.

Every step must be retryable. Unique external IDs, event IDs, content hashes, and computation-version keys make retries idempotent.

### 8.5 Storage design

PostgreSQL should hold relational records and compact derived values. Object storage should hold immutable or large artifacts.

Core entities should include:

- User, profile, preferences, device/session.
- External connection, encrypted token reference, granted scopes, consent record.
- Source event, ingestion job, source payload/file, checksum, processing state.
- Activity, activity source, lap/split summary, stream artifact.
- Daily health observation with source, observed time, received time, and quality.
- Metric definition, metric value, calculation version, confidence/quality flags.
- Goal, availability/constraints, training plan, immutable plan revision.
- Planned session, workout prescription, user override, approval event.
- Activity-session match and adherence assessment.
- Recommendation, evidence references, inputs snapshot, model/prompt version.
- Product, purchase transaction, entitlement interval, subscription event.
- Data export, deletion request, retention action, security audit event.

Every user-owned row must have an immutable tenant/user key. Enforce isolation in repository/query APIs and add PostgreSQL row-level security as defense in depth for the most sensitive tables. Test cross-tenant denial directly.

Do not store absolute local file paths. Store object keys and metadata. Do not use `INSERT OR REPLACE` semantics that can accidentally reset provenance fields; model source revisions explicitly.

### 8.6 API design

Expose a versioned REST API with an OpenAPI contract. Mobile clients should receive product-oriented resources, not database rows:

- Current athlete state with freshness and quality.
- Paginated activities and an activity analysis projection.
- Trends with units, source, confidence, and calculation version.
- Goal and current plan revision.
- Proposed plan change and explicit approve/reject actions.
- Subscription entitlement and available product capabilities.
- Connection, consent, export, and deletion status.

Use cursor pagination and conditional requests. Avoid making the mobile client download per-second streams to draw every chart; provide downsampled series appropriate to the viewport and keep raw export separate.

## 9. Analytics and data-quality redesign

### 9.1 Preserve formulas as versioned domain behavior

The current analytics modules are the best candidates for intentional reuse, but first convert each formula into a documented metric contract:

- Definition and unit.
- Required source fields.
- Inclusion/exclusion rules.
- Missing-data behavior.
- Minimum sample duration/density.
- Device/sport limitations.
- Expected numeric examples and golden fixtures.
- Confidence/quality output.
- Formula version and change policy.

Never overwrite historical derived values without retaining the calculation version. A formula correction should trigger a controlled recomputation and allow support to explain why a number changed.

### 9.2 Do not use ACWR as an injury oracle

The current prototype describes a 0.8–1.3 ACWR "sweet spot." This is too strong for a production coaching product. A methodological review concluded that causal injury reduction from manipulating ACWR has not been established and warned that the ratio can create artifacts. See [Impellizzeri et al., *Acute:Chronic Workload Ratio: Conceptual Issues and Fundamental Pitfalls*](https://pubmed.ncbi.nlm.nih.gov/32502973/).

Recommended treatment:

- Keep recent-versus-baseline load as one descriptive signal if users find it useful.
- Label it as a workload comparison, not an injury probability.
- Never make a hard plan decision from ACWR alone.
- Combine recent load, monotony, history, recovery observations, session intensity, user feedback, and data quality.
- Use conservative deterministic progression limits that are configurable and reviewed by a qualified sport scientist.
- Show uncertainty and the reason for any recommendation.

### 9.3 Recovery signals require baselines and uncertainty

HRV, sleep, resting HR, readiness, and subjective state are noisy and device-dependent. HRV-guided training evidence suggests potentially useful but modest and method-sensitive effects; it does not justify a single-night automatic verdict. See this [systematic review and meta-analysis](https://pubmed.ncbi.nlm.nih.gov/34639599/).

The recovery engine should:

- Build a personal rolling baseline only after sufficient valid observations.
- Distinguish missing, late, corrected, and physiologically unusual data.
- Prefer trends and multiple signals over one measurement.
- Allow the athlete to add soreness, illness, sleep disruption, and perceived fatigue.
- Produce `normal`, `caution`, or `insufficient_data` rather than false precision.
- Make severe symptom reporting direct the user to appropriate professional care, not an AI-generated workout.

### 9.4 Data quality is a first-class output

Every chart and coach input should carry:

- Source system and device where available.
- Observation and ingestion timestamps.
- Completeness/density.
- Metric era—whether a sensor existed at that time.
- Confidence or reason unavailable.
- Calculation version.
- Staleness.

The UI should display "not enough data" instead of drawing a persuasive trend through sparse history.

## 10. Coaching architecture and safety

### 10.1 The LLM must not be the plan engine

In the current code, the LLM receives a summary and returns the plan structure. That is useful for prototyping but gives a probabilistic text model authority over load progression, session order, recovery adjustments, and citations.

Production should separate responsibilities:

1. **Deterministic state calculation**: fitness/load/recovery/data quality.
2. **Constraint model**: goal date, days available, max duration, current volume, recent intensity, equipment, injuries/limitations, no-consecutive-hard-days rules, taper bounds.
3. **Plan generator**: creates sessions from a controlled taxonomy and validates the schedule against constraints.
4. **Safety validator**: rejects invalid volume jumps, incompatible sessions, target dates, missing prerequisites, and unsafe combinations.
5. **LLM explanation layer**: explains the validated plan, summarizes tradeoffs, and proposes only actions from a bounded schema.
6. **User approval**: material changes create a new proposed revision; they do not silently mutate the active plan.

If the LLM is unavailable, the user should still see metrics and the current plan. If the deterministic validator is unavailable or rejects output, no new plan is published.

### 10.2 Controlled session taxonomy

Define a versioned workout vocabulary before implementing adaptive plans:

- Rest.
- Recovery run.
- Easy aerobic run.
- Long run.
- Steady/tempo.
- Threshold intervals.
- VO2-oriented intervals.
- Strides/hill sprints.
- Race/simulation.
- Strength/mobility.
- Cross-training.

Each type needs prescription fields, allowed intensity anchors, warm-up/cool-down requirements, Garmin Training API mapping, adherence rules, and contraindication/guardrail rules. Free-form LLM descriptions can supplement these fields but cannot replace them.

### 10.3 Plan revisions and auditability

Plans should be immutable revisions. Record:

- Input data snapshot and freshness.
- Goal and user constraints.
- Analytics, rule-set, knowledge, model, and prompt versions.
- Proposed sessions and validator result.
- Explanation and evidence references.
- User approval/rejection and timestamp.
- Later manual edits and reason.

This preserves the prototype's "you in the loop" intent and makes support, safety investigation, and reproducibility possible.

### 10.4 Adherence matching

Replace the current nearest-session greedy matcher with an explicit matching/scoring service:

- Generate candidates within a bounded time window.
- Score sport, planned type, duration/distance, intensity pattern, intervals, and date distance.
- Auto-match only above a confidence threshold.
- Let users correct a match.
- Store match method and confidence.
- Recompute adherence after a correction without altering the source activity.

Execution scoring must be session-specific. An easy run is not graded by the same rules as intervals or a long run.

### 10.5 Knowledge governance

Do not let a production job autonomously browse the web and promote its own findings into the coaching knowledge base.

Use a reviewed evidence registry:

- Stable source identifier, DOI/URL, publication metadata, and topic.
- Exact supported claim in the product's own words.
- Population and limitations.
- Evidence grade and review date.
- Reviewer identity and approval.
- Superseded/retracted status.
- Which rules or explanations use the source.

The LLM may retrieve from approved claims. It may not invent citations, cite a source for a claim the source does not support, or turn observational association into causal guidance.

### 10.6 Product claims

Market the app as fitness analysis and coaching support, not diagnosis, treatment, injury prediction, or medical monitoring. Legal review is required for launch claims in each territory. A disclaimer does not repair unsafe product behavior or misleading marketing.

## 11. Privacy, compliance, and data governance

This section is engineering guidance, not legal advice. Counsel should review the actual company jurisdiction, launch territories, Garmin agreement, privacy policy, terms, and product claims.

### 11.1 Treat the dataset as highly sensitive

Activities can reveal home/work locations and routines. Heart rate, sleep, stress, HRV, body composition, and recovery are health-related. Goals, notes, and AI prompts may reveal injury or illness. The combined dataset is substantially more sensitive than an ordinary fitness activity list.

Design decisions:

- No advertising SDKs.
- No sale of user data.
- No health/activity data in product analytics, crash reports, support tools, or logs.
- No precise GPS in push-notification payloads.
- No production data in development or test.
- No broad employee database access.
- No model training on user data without separate, explicit, optional consent and legal review.

Apple requires a public privacy policy and App Privacy disclosures, including relevant behavior of third-party SDKs. Apple also imposes additional restrictions on health/fitness data and prohibits storing personal health information in iCloud. See [Apple's App Privacy details](https://developer.apple.com/app-store/app-privacy-details/) and [App Review Guidelines](https://developer.apple.com/app-store/review/guidelines/).

### 11.2 GDPR/EEA implications

For EEA users, health data is a special category under GDPR Article 9. The product needs both an Article 6 legal basis and an Article 9 condition, likely explicit consent for core health-data processing, subject to counsel's assessment. Consent must be specific, informed, recorded, and withdrawable. Users also have access and erasure rights, and transfers outside the EEA require an appropriate mechanism. See the official [GDPR text](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32016R0679).

Complete a Data Protection Impact Assessment before public launch because the product systematically processes sensitive data and performs profiling/coaching. Document purposes, data flows, processors, retention, risks, mitigations, and automated decision behavior.

### 11.3 United States implications

Do not assume HIPAA applies merely because data is health-related; a direct-to-consumer app may instead fall outside HIPAA. That does not mean it is unregulated. The FTC states that an app which collects consumer information and syncs with a fitness tracker is probably a vendor of personal health records under its Health Breach Notification Rule. The amended rule applies to many health apps and includes unauthorized disclosures as well as conventional intrusions. See the FTC's [compliance guidance](https://www.ftc.gov/business-guidance/resources/complying-ftcs-health-breach-notification-rule-0).

Create a breach-response plan before launch, including vendor notification duties, evidence preservation, decision ownership, notification timelines, and pre-approved communication templates.

### 11.4 Israeli operator implications

If the operating entity is Israeli, obtain local counsel review under the Privacy Protection Law, the Data Security Regulations, and Amendment 13. The Israeli Privacy Protection Authority states that a database with specially sensitive personal information on more than 100,000 people has a notification obligation, and Amendment 13 changes database registration/notification and privacy-officer requirements. Scale thresholds are not a reason to postpone basic compliance. See the Authority's [Amendment 13 preparation page](https://govextra.gov.il/privacy-protection-regulations/privacy-protection-regulations/) and [database guidance](https://www.gov.il/he/service/registration_in_the_database).

### 11.5 Retention and deletion

Define retention per artifact, not one policy for the whole account:

- OAuth tokens: until disconnect/revocation, then delete promptly.
- Raw webhook payloads: short diagnostic retention unless needed as the source record.
- Raw FIT: only as long as necessary for promised recalculation/export.
- Normalized and derived metrics: while account and consent remain active, subject to tier policy.
- AI prompts/results: minimized, with a shorter explicit retention where possible.
- Security audit logs: longer, with sensitive fields excluded.
- Billing records: legally required retention, logically separated from deleted health data.
- Backups: expire on a documented schedule; deleted users must not return to active tables after restore.

Account deletion should be an orchestrated, auditable process covering the primary database, object storage, search/cache, AI provider where supported, support tools, identity provider, push tokens, and Garmin authorization. Backups should age out rather than be individually rewritten, with restored data immediately re-subjected to deletion tombstones.

## 12. Security architecture

### 12.1 Baseline controls

- TLS everywhere and strict transport security.
- Encryption at rest with managed keys.
- Application-level envelope encryption for Garmin refresh tokens and especially sensitive notes.
- Secret manager; no long-lived secrets in repository or environment files on developer machines.
- Short-lived user sessions, refresh-token rotation, device/session revocation.
- OAuth state, PKCE where applicable, nonce, exact redirect allowlist, and account-linking protections.
- Signed/authenticated Garmin and Apple webhook verification before processing.
- Least-privilege service identities and separate production/staging accounts.
- Egress restrictions for workers handling health data.
- Rate limits and abuse controls on auth, export, delete, coach, and webhook endpoints.
- Immutable security audit trail for privileged data access and account changes.
- Dependency scanning, secret scanning, static analysis, container scanning, and signed deployments.
- Independent penetration test before broad launch and after major auth/data-flow changes.

### 12.2 Logging and observability rules

Use correlation IDs, internal user IDs only when necessary, event types, durations, result codes, and counts. Redact:

- Garmin and Apple tokens.
- Email and external account identifiers.
- Raw payloads.
- GPS coordinates and activity names.
- Health observations.
- Goals, notes, prompts, and generated coaching text.

Error reporting SDKs must be configured before integration, not trusted at defaults.

### 12.3 LLM data boundary

Before selecting an LLM provider, require:

- Contract/DPA appropriate to launch territories.
- No provider training on submitted data.
- Defined retention and deletion controls.
- Regional processing/transfer documentation.
- Security and subprocessors review.
- Ability to use pseudonymous requests.

Send the smallest computed context required. Do not send raw FIT, GPS routes, Garmin identifiers, email, or full health payloads. Separate evidence retrieval from user context where possible.

## 13. Reliability and operations

### 13.1 User-visible reliability targets

Set initial service objectives before beta:

- Authenticated API availability target.
- Garmin event acknowledgment latency.
- Recent activity visible within a target period after Garmin delivery.
- Backfill completion target by history size.
- Subscription entitlement convergence target.
- Data export completion target.
- Account deletion completion target.

The UI must distinguish Garmin delay, queued processing, failed processing, stale authorization, insufficient data, and product outage.

### 13.2 Failure handling

- Retry transient Garmin/Apple/LLM failures with exponential backoff and jitter.
- Do not retry invalid payloads indefinitely.
- Dead-letter failed jobs with redacted diagnostics and an operator replay action.
- Circuit-break degraded external providers.
- Keep ingestion independent from AI generation.
- Reconcile Garmin data periodically because webhook delivery cannot be the sole source of truth.
- Reconcile Apple entitlement state periodically because notifications can be delayed.
- Use database outbox/inbox patterns for state changes that must produce jobs.
- Make every state transition observable and idempotent.

### 13.3 Backup and recovery

- Point-in-time recovery for PostgreSQL.
- Versioning/retention protection for critical object storage.
- Documented recovery point and recovery time objectives.
- Quarterly restore exercises into an isolated environment.
- Automated verification that tenant isolation and deletion tombstones still apply after restore.

## 14. Testing and release quality

The new repository should begin with tests and delivery controls, not add them after feature parity.

### 14.1 Required test layers

- **Metric unit tests**: numeric examples, edge cases, units, missing fields.
- **Golden FIT tests**: synthetic or properly licensed fixtures across device/sport variants.
- **Property tests**: invariants such as non-negative durations and stable idempotent recomputation.
- **Garmin contract tests**: approved sandbox payloads, OAuth, correction, deletion, and quota behavior.
- **API contract tests**: generated client compatibility and authorization.
- **Tenant isolation tests**: attempt cross-user access for every resource family.
- **Job tests**: duplicate, reordered, delayed, poison, and partial events.
- **Subscription tests**: StoreKit sandbox plus every relevant Server Notification V2 transition.
- **Coach safety/evaluation suite**: constraint violations, sparse data, illness/injury text, hallucinated citations, adversarial goals, and degraded inputs.
- **Mobile UI/accessibility tests**: Dynamic Type, VoiceOver, reduced motion, dark/light appearance as supported, offline/stale states.
- **End-to-end synthetic journey**: account → Garmin sandbox → ingest → free dashboard → purchase → plan → approval → workout publish → downgrade → export/delete.

### 14.2 Release controls

- Pull-request review and required CI.
- Reproducible locked dependencies.
- Database migrations reviewed separately and tested against production-like volume.
- Infrastructure changes reviewed as code.
- Separate dev, staging, and production accounts with no shared data/secrets.
- Feature flags for risky coach and Garmin-publishing features.
- Phased App Store rollout and kill switches for sync, AI generation, and workout publishing.
- Rollback procedure that respects schema compatibility.

For App Review, provide a synthetic fully featured demo mode or review account. Apple asks account-based apps to provide a demo account or fully featured demo mode and any hardware/resources needed for review. Reviewers should not need to provide a personal Garmin account.

## 15. Migration and reuse plan

### 15.1 What to carry forward

- Domain vocabulary from `SPEC.md`.
- Desired source fidelity and incremental sync behavior.
- FIT parsing lessons and field mappings, after fixture tests.
- Metric definitions that pass scientific and numeric review.
- Dashboard information hierarchy and explanations.
- The athlete-approved plan-change principle.
- Schedule/override interaction learnings.
- The LLM provider abstraction as a concept, not the local CLI implementation.

### 15.2 What not to carry forward

- Garmin consumer credentials/session handling.
- SQLite and shared filesystem persistence.
- JSON files as mutable plan/recommendation state.
- In-request sync and LLM work.
- Local Claude/Codex CLI execution.
- Unverified autonomous research output.
- Hard-coded athlete thresholds and fixed HR filters.
- Global paths/configuration and implicit single-user queries.
- Existing personal data and tokens.

### 15.3 How to port safely

For each reusable analytic behavior:

1. Write a metric contract and expected examples.
2. Capture synthetic/golden input and current output.
3. Review the science, units, missing-data behavior, and personalization assumptions.
4. Implement it in the new pure domain package.
5. Compare old/new results and explain intentional differences.
6. Assign a production calculation version.

The old repository remains a visual/product sandbox. New ideas can be tried locally, but production receives them only through reviewed contracts, tests, privacy review, and release controls.

Do not automatically migrate the owner's personal prototype account into the SaaS. Enroll through the same official consent flow as every other user. A later import tool can accept user-exported FIT files if Garmin terms permit it.

## 16. Delivery plan and gates

### Phase 0: feasibility and product controls

Deliverables:

- Garmin business application and private API review.
- Field-level capability/licensing matrix.
- Independent product name and brand review.
- Launch territory decision.
- Privacy data map, initial DPIA/threat model, processor list.
- Adult recreational runner scope and claims policy.
- Free/Premium entitlement specification.
- Session taxonomy and coaching safety rules reviewed by a qualified endurance professional.

Exit gate: official Garmin access is viable and required premium inputs are known. If not, change the product promise before engineering the platform.

### Phase 1: production foundation

Deliverables:

- Production monorepo, ADRs, CI/CD, environments, migration system.
- Product authentication and account lifecycle.
- Garmin OAuth, consent record, disconnect/revoke.
- Durable webhook/inbox/queue pipeline.
- PostgreSQL/object storage with tenant isolation and encryption.
- Synthetic fixture and observability foundations.

Exit gate: two synthetic users cannot access each other's data; duplicate/out-of-order events are safe; token revocation and deletion work end to end.

### Phase 2: Free MVP

Deliverables:

- Recent activity/health backfill and ongoing sync.
- Activity list, last-activity view, basic load/recovery/volume trends.
- Data quality/freshness states.
- iOS onboarding and web account/privacy portal.
- Export and in-app account deletion.
- App Review demo mode.

Exit gate: external beta users get a useful result without staff intervention and can fully disconnect/export/delete.

### Phase 3: Premium analytics and commerce

Deliverables:

- Deep activity analysis and longer comparisons.
- StoreKit 2 products, server notifications, entitlement ledger, restore/manage flows.
- Premium gates enforced by the server and represented consistently in iOS/web.
- Subscription support/admin tooling with no health-data exposure.

Exit gate: every subscription transition passes sandbox and reconciliation tests; a refunded or expired entitlement converges correctly.

### Phase 4: constrained coach

Deliverables:

- Goal/availability/constraint model.
- Controlled session taxonomy and deterministic plan generator/validator.
- Immutable plan revisions, approvals, activity matching, adherence.
- Reviewed evidence registry.
- Bounded LLM explanations and proposals with evaluation suite.
- Garmin Training API publishing for approved sessions.

Exit gate: unsafe or invalid generated plans are rejected automatically; every displayed plan is reproducible from an input/version record; no workout is pushed without user authorization.

### Phase 5: hardening and broader release

Deliverables:

- Load/cost testing, SLO alerts, runbooks, restore drill.
- Independent penetration test and remediation.
- Legal/App Store/Garmin brand review.
- Incident and breach exercise.
- Phased launch, support operations, product analytics using non-sensitive events.

Exit gate: the team can detect, explain, contain, and recover from realistic failures without inspecting raw user health data casually.

### Indicative effort

This is not a one-developer wrapper around the existing dashboard. After Garmin access, a credible iOS-first beta is roughly a multi-quarter effort for a small team with backend/data, iOS, product design, and part-time security/privacy/sport-science support. A solo implementation is possible only by reducing scope sharply—Free analytics first, one territory, no adaptive AI coach, and no workout publishing—and accepting a longer schedule.

## 17. Principal risks

| Risk | Impact | Mitigation / decision |
|---|---|---|
| Garmin rejects access or omits required metrics | Product promise cannot be delivered | Phase 0 gate; define a reduced feature set before platform build |
| Unofficial integration is used as a shortcut | Credential, terms, rate-limit, and review risk | Prohibit it in production architecture |
| Coaching produces unsafe or unjustified advice | User harm, trust loss, regulatory/brand exposure | Deterministic constraints, reviewed taxonomy, evidence registry, approval, evaluation suite |
| Cross-tenant data leak | Severe sensitive-data breach | Tenant keys, RLS defense, authz tests, least privilege, penetration test |
| LLM/vendor receives excess health data | Privacy breach and compliance exposure | Data minimization, pseudonymization, DPA, no-training terms, egress and logging controls |
| Subscription state diverges across device/server/web | Incorrect access or support burden | Entitlement ledger, StoreKit verification, V2 notifications, periodic reconciliation |
| Backfill takes too long or exceeds quotas | Poor onboarding and support load | Recent-first processing, progress states, quota-aware queues, resumable backfill |
| Metrics look precise despite sparse/noisy data | Misleading product decisions | Quality flags, minimum density, personal baselines, insufficient-data states |
| Costs grow with raw streams and AI | Poor unit economics | Retention tiers, compressed artifacts, downsampling, event-driven cached AI, fair-use limits |
| App Review cannot access Garmin-dependent features | Rejection/delay | Synthetic fully featured review mode and clear review notes |
| Product name/UX implies Garmin affiliation | Trademark/agreement/review issues | Independent brand and Garmin guideline review |

## 18. Decisions to make before implementation

The following are product decisions, not details to leave to individual engineers:

1. Legal entity and first launch territories.
2. Independent product name.
3. Exact Garmin APIs, fields, quotas, licenses, and derived-data permissions.
4. Whether version 1 supports Garmin only or also user FIT import/Apple Health.
5. Free history window and downgrade retention.
6. Premium monthly/annual products, trial, family-sharing policy, and fair-use limits.
7. Whether workout publishing is launch-critical or post-launch.
8. Adult-only minimum age and how it is enforced.
9. Session taxonomy, progression constraints, and qualified reviewer.
10. LLM provider, region, retention, DPA, and fallback behavior.
11. Cloud/region and data-residency posture.
12. Customer support access model and sensitive-data escalation process.
13. Product claims and when users are directed to a human coach or clinician.

## 19. Recommended immediate next actions

In order:

1. Apply to the Garmin Connect Developer Program with Activity, Health, and Training API requirements.
2. Produce the field-level API/licensing matrix from Garmin's private documentation.
3. Freeze a narrow Free/Premium product contract based on confirmed data.
4. Have privacy counsel map the intended territories, entity, processors, consent, and retention obligations.
5. Have a qualified sport scientist review the metric claims, ACWR presentation, recovery rules, and initial session taxonomy.
6. Create the new production repository with domain glossary, ADRs, threat model, data map, and test/CI foundation before feature work.
7. Build the official OAuth-to-recent-activity vertical slice first: product login → Garmin consent → one activity → validated metric → iOS display → disconnect/delete.
8. Add the Free MVP before subscriptions or AI coaching.
9. Add commerce, then constrained coaching, each behind separate release gates.

The tracer-bullet vertical slice in step 7 is the most important implementation proof. It exercises identity, official consent, sensitive-data storage, ingestion, tenancy, calculation provenance, API contracts, iOS presentation, and deletion without prematurely building the entire feature catalog.

## 20. Conclusion

The current repository has already done the difficult exploratory work: it shows which Garmin data is valuable, which analyses are understandable, and why an integrated coaching loop is more compelling than another activity feed. Its value is product and domain discovery.

The production successor must solve a different problem. It must earn authorization rather than accept credentials, isolate many users rather than trust one machine, preserve provenance rather than overwrite files, survive retries rather than run synchronously, enforce subscriptions across platforms, protect health/location data, and constrain AI coaching so that the system remains explainable and safe.

The correct strategy is therefore a clean production monorepo, built through an official Garmin vertical slice and gated by data availability, privacy, security, and coaching evidence. Reuse the prototype's tested behavior and interaction lessons; replace its operating assumptions.
