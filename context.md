# Project Context: Fake News Detector (MVP)

## 1. Objective
Build an MVP backend for a fake news detection platform using Django + PostgreSQL. The system should help users verify whether a claim is true, false, or uncertain through automated analysis plus community fact-checking.

## 2. Product Scope (MVP)
The platform supports claim verification with:
- Automated first-pass answer from the system
- Community discussion/fact-checking thread (similar to Q&A flow)
- Reputation and badge-based incentives for useful contributors

This is an MVP, so focus on core workflows, correctness, and maintainability.

## 3. User Roles
- Normal User: submit claims/questions, vote, comment.
- Journalist (verified): can submit higher-trust fact checks and evidence.
- Admin: moderates content, approves journalist verification requests.

Journalist verification flow:
- User uploads work ID/proof.
- Admin manually reviews and approves/rejects.

## 4. Data Sources
Initial trusted inputs:
- RSS news feeds
- Trusted newspaper sources
- Official statements
- Previous verified reports

## 5. Core Workflow
1. User submits a claim/query.
2. System creates a claim thread automatically.
3. System posts an initial machine-generated answer with confidence.
4. Users and journalists add evidence-based fact checks.
5. Community voting and moderation refine credibility.
6. Reputation points and badges are awarded for high-quality contributions.

## 6. Reputation Rules (Initial)
Increase reputation when a user:
- Submits valid claims
- Reports misinformation correctly
- Receives upvotes on high-quality fact checks

## 7. Technical Context
- Backend: Django (API-first with DRF)
- Database: PostgreSQL
- Environment: must run both locally and production
- Current repository stage: early setup; custom user model planned

## 8. What I Need From AI/Architect Review
When comparing implementation options, provide:
- Top 3 industry-standard choices relevant to this stack
- Trade-offs (performance, complexity, risk)
- Rough cost implications
- Setup complexity (low/medium/high)
- One recommended option for MVP, with short justification
