PHASE 0 — Master requirement prompt
Sabse pehle Copilot ko ye complete project context do:
I want to build a production-style AI-powered Automated Bank Dispute Resolution and Escalation System using Python.
 
Project objective:
Build an intelligent system that can understand banking customer disputes, classify them, authenticate/verify the customer and transaction using mock banking APIs, retrieve relevant bank policies using RAG, apply deterministic banking rules, assess risk, automatically resolve eligible low-risk disputes, and escalate complex/high-risk disputes to human agents.
 
Use only synthetic/mock banking data during development. Do not use real customer, account, card, transaction, or personally identifiable information.
 
Core dispute types:
1. UPI failed but amount debited
2. UPI transaction pending
3. ATM cash not received but account debited
4. Unauthorized card transaction
5. Card payment reversed/failed
6. Refund not received
7. NEFT/RTGS/IMPS transaction issue
8. Wrong bank fee/charge
9. Loan EMI dispute
10. Credit card billing dispute
 
Technology stack:
- Python 3.11+
- FastAPI
- Pydantic
- PostgreSQL
- SQLAlchemy
- LangChain
- LangGraph
- RAG
- Sentence Transformers or configurable embedding provider
- FAISS or Chroma
- Configurable LLM provider
- PyMuPDF/Docling for document ingestion
- pytest
- Docker
- Docker Compose
- GitHub Actions
- structured logging
- LangSmith-compatible tracing
- JWT/OAuth-style authentication for APIs
- React frontend or Streamlit initially if React is too large for the first version
 
Architecture:
Customer/API
→ Authentication
→ Dispute Intake
→ Intent Classification
→ Customer Verification
→ Transaction Verification
→ Policy Retrieval using RAG
→ Rules Engine
→ Risk/Fraud Assessment
→ Resolution Decision
→ Auto Resolution OR Human Escalation
→ Notification
→ Audit Logging
 
Use modular architecture and clean code principles.
 
Do not put business logic directly inside FastAPI routes.
Do not allow the LLM to directly execute financial actions.
All financial actions must pass through deterministic validation and authorization rules.
Every decision and action must be audit logged.
 
Before writing code, first create:
1. Detailed architecture
2. Component responsibilities
3. Folder structure
4. Database schema
5. API design
6. LangGraph workflow
7. RAG pipeline design
8. Rules engine design
9. Security design
10. Testing strategy
11. Deployment strategy
 
Do not start implementation until the architecture is clearly defined.
PHASE 1 — Project structure
Architecture approve karne ke baad:
Now create the complete project folder structure based on the approved architecture.
 
Use a clean modular Python architecture.
 
Create folders for:
- app/api
- app/core
- app/models
- app/schemas
- app/services
- app/agents
- app/workflows
- app/rag
- app/rules
- app/database
- app/tools
- app/security
- app/notifications
- app/audit
- tests
- data
- documents
- scripts
- frontend
- deployment
 
Also create:
- requirements.txt
- pyproject.toml
- .env.example
- .gitignore
- README.md
- Dockerfile
- docker-compose.yml
 
Do not put secrets in source code.
 
Explain the responsibility of every directory and file before creating implementation code.
PHASE 2 — Database
Now implement the database layer using PostgreSQL, SQLAlchemy and Pydantic.
 
Create models/tables for:
 
1. Customer
2. Account
3. Card
4. Transaction
5. Dispute
6. DisputeEvent
7. Resolution
8. Escalation
9. PolicyMetadata
10. AuditLog
11. Notification
 
Requirements:
 
- Use UUID primary keys where appropriate.
- Add created_at and updated_at timestamps.
- Add appropriate indexes.
- Define proper foreign-key relationships.
- Do not store sensitive data unnecessarily.
- Mask account/card numbers when returned through APIs.
- Use enums for transaction status, dispute status, dispute category, priority and escalation status.
- Add database constraints wherever possible.
 
Create:
- SQLAlchemy models
- Pydantic schemas
- database connection module
- session management
- migration-ready structure
- seed script with synthetic banking data
 
Create at least:
- 100 synthetic customers
- synthetic accounts
- synthetic cards
- 500+ transactions
- sample disputes
 
Do not use real banking/customer information.
PHASE 3 — Mock banking tools
Ye project ka bahut important part hai.
Now implement mock banking service tools.
 
Create tools/services for:
 
get_customer(customer_id)
authenticate_customer(customer_id, verification_data)
get_customer_accounts(customer_id)
get_customer_transactions(customer_id)
get_transaction(transaction_id)
check_transaction_status(transaction_id)
check_refund_status(transaction_id)
check_previous_disputes(customer_id)
check_card_status(card_id)
check_account_status(account_id)
 
Dispute actions:
create_dispute()
update_dispute()
create_refund_request()
create_provisional_credit_request()
escalate_dispute()
send_customer_notification()
 
Important:
These are mock/sandbox banking operations only.
 
Each tool must:
- validate input
- check authorization
- return structured Pydantic responses
- log the action
- never expose sensitive data unnecessarily
 
Do not allow the LLM to directly access the database.
The LLM must call controlled tools instead.
PHASE 4 — Dispute classification
Now implement the dispute classification service.
 
Input:
Natural-language customer complaint.
 
Output:
Structured object:
 
{
    dispute_category,
    transaction_type,
    urgency,
    confidence,
    required_information,
    fraud_indicator
}
 
Supported categories:
- UPI_FAILED
- UPI_PENDING
- ATM_CASH_NOT_RECEIVED
- UNAUTHORIZED_CARD_TRANSACTION
- CARD_PAYMENT_FAILED
- REFUND_NOT_RECEIVED
- NEFT_RTGS_IMPS_ISSUE
- WRONG_BANK_CHARGE
- LOAN_EMI_DISPUTE
- CREDIT_CARD_BILLING_DISPUTE
- UNKNOWN
 
Use an LLM-based classifier with structured output.
 
Add deterministic fallback rules for obvious cases.
 
If confidence is below the configured threshold:
mark the case for clarification or human review.
 
Do not make any financial decision during classification.
Add unit tests for every category.
PHASE 5 — RAG
Ab banking policies ke documents ke liye RAG banao.
Now implement the complete banking policy RAG pipeline.
 
Input documents will be placed under:
documents/policies/
 
The pipeline must:
 
1. Load PDF/DOCX/Markdown/text documents.
2. Extract text using PyMuPDF or Docling.
3. Preserve document metadata.
4. Clean the extracted text.
5. Split into meaningful chunks.
6. Generate embeddings.
7. Store embeddings in FAISS or Chroma.
8. Persist the index.
9. Support semantic retrieval.
10. Return source document and page/section metadata.
 
Metadata should include:
- policy_id
- document_name
- document_version
- effective_date
- category
- page
- section
 
Create:
- ingestion script
- embedding service
- vector store
- retriever
- retrieval service
- configuration
 
The RAG response must contain citations/source metadata.
 
Never allow the LLM to invent bank policy.
If no relevant policy is found, return NO_POLICY_FOUND.
PHASE 6 — Rules Engine
Ye banking system ka core safety layer hoga.
Now implement a deterministic banking dispute rules engine.
 
The rules engine must operate independently from the LLM.
 
Create rules for:
 
1. UPI failed + amount debited
2. UPI pending
3. ATM cash not received + amount debited
4. Unauthorized card transaction
5. Refund not received
6. NEFT/RTGS/IMPS failed
7. Wrong bank charge
8. Loan EMI dispute
9. Credit card billing dispute
 
Each rule must evaluate:
- transaction status
- transaction type
- amount
- customer verification status
- previous dispute status
- fraud indicators
- policy eligibility
- time/TAT conditions
 
Return:
 
{
    eligible_for_auto_resolution,
    recommended_action,
    reason_codes,
    required_human_review,
    risk_level
}
 
Never let the LLM override these rules.
 
Create unit tests for every rule including positive and negative cases.
PHASE 7 — Risk/Fraud engine
Now implement a dispute risk assessment module.
 
Create a configurable risk scoring system using synthetic data.
 
Features can include:
- transaction amount
- transaction type
- transaction status
- customer dispute frequency
- previous fraud indicators
- unusual transaction characteristics
- authentication status
- transaction age
 
Initially implement a deterministic scoring model.
 
Return:
 
risk_score
risk_level
risk_factors
recommended_action
 
Risk levels:
LOW
MEDIUM
HIGH
CRITICAL
 
For HIGH or CRITICAL cases:
require human review.
 
Keep the scoring module independent so that an ML model such as XGBoost can be added later.
 
Create tests for the scoring logic.
PHASE 8 — LangGraph
Ab actual Agentic workflow banao:
Now implement the complete LangGraph-based dispute resolution workflow.
 
Create a typed graph state containing:
 
- customer_id
- dispute_id
- customer_message
- dispute_category
- transaction_id
- customer_verified
- transaction_verified
- retrieved_policies
- rule_result
- risk_result
- resolution_decision
- action_result
- escalation_required
- final_response
- errors
- audit_context
 
Nodes:
 
1. intake_node
2. classify_dispute_node
3. authenticate_customer_node
4. identify_transaction_node
5. verify_transaction_node
6. retrieve_policy_node
7. evaluate_rules_node
8. assess_risk_node
9. resolution_decision_node
10. execute_safe_action_node
11. escalation_node
12. notification_node
13. audit_node
 
Conditional routing:
 
classification failure
→ clarification/human review
 
authentication failure
→ stop/escalate
 
transaction verification failure
→ clarification/human review
 
high/critical risk
→ human escalation
 
rule not eligible
→ human escalation
 
eligible + low risk
→ safe automated action
 
Every node must have:
- typed input/output
- error handling
- structured logging
- audit event generation
 
The LLM must never bypass authentication, deterministic rules, risk checks, or authorization.
PHASE 9 — Human escalation
Now implement the human-in-the-loop escalation system.
 
Create escalation reasons:
- HIGH_RISK
- FRAUD_SUSPECTED
- POLICY_NOT_FOUND
- LOW_CLASSIFICATION_CONFIDENCE
- CUSTOMER_NOT_VERIFIED
- TRANSACTION_NOT_FOUND
- RULE_NOT_ELIGIBLE
- HIGH_VALUE_TRANSACTION
- REPEATED_DISPUTE
- SYSTEM_ERROR
 
Create:
- escalation record
- priority
- reason
- assigned_team
- assigned_agent
- SLA/TAT
- status
- timestamps
- agent notes
 
Implement APIs for:
- create escalation
- get escalation
- assign escalation
- update escalation
- resolve escalation
 
Create a simple human-agent dashboard.
PHASE 10 — FastAPI
Now expose the dispute resolution system through FastAPI.
 
Create APIs:
 
POST /api/v1/disputes
POST /api/v1/disputes/classify
GET /api/v1/disputes/{dispute_id}
GET /api/v1/disputes/{dispute_id}/status
POST /api/v1/disputes/{dispute_id}/resolve
POST /api/v1/disputes/{dispute_id}/escalate
 
Customer APIs:
GET /api/v1/customers/{customer_id}
GET /api/v1/customers/{customer_id}/transactions
 
Transaction APIs:
GET /api/v1/transactions/{transaction_id}
 
Agent APIs:
GET /api/v1/escalations
GET /api/v1/escalations/{id}
POST /api/v1/escalations/{id}/assign
POST /api/v1/escalations/{id}/resolve
 
Add:
- Pydantic validation
- authentication
- authorization
- error handling
- HTTP status codes
- OpenAPI documentation
- request IDs
- structured logging
 
Routes must only orchestrate services.
Business logic must remain in service/rules/workflow layers.
PHASE 11 — Security
Now implement security controls.
 
Requirements:
 
1. JWT-based API authentication
2. Role-based authorization
3. Roles:
   - CUSTOMER
   - SUPPORT_AGENT
   - DISPUTE_MANAGER
   - ADMIN
 
4. Mask account numbers and card numbers.
5. Never log passwords, tokens, CVV, full card numbers or sensitive authentication data.
6. Validate all API inputs.
7. Add rate limiting configuration.
8. Secure environment variables.
9. Add CORS configuration.
10. Add security headers where applicable.
11. Add audit logging for sensitive actions.
 
Create a security configuration module.
 
Use only synthetic data in development.
PHASE 12 — Notifications
Now implement a notification service.
 
Support:
- email notification
- SMS mock notification
- in-app notification
 
Create templates for:
 
1. Dispute created
2. Dispute under review
3. Automatic resolution
4. Refund initiated
5. Escalated to human agent
6. Dispute resolved
7. Additional information required
 
For development, use mock notification providers.
 
Do not send real messages.
Log notification delivery status.
PHASE 13 — Audit trail
Now implement a complete audit trail.
 
Every important action must generate an immutable audit event.
 
Track:
- request_id
- dispute_id
- customer_id
- actor_type
- actor_id
- event_type
- event_description
- previous_state
- new_state
- timestamp
- tool/action executed
- policy references
- decision reason
 
Audit events should cover:
- authentication
- classification
- transaction lookup
- policy retrieval
- rule evaluation
- risk assessment
- resolution
- refund request
- escalation
- human agent action
- notification
 
Do not log sensitive secrets or full payment credentials.
PHASE 14 — Frontend
Agar React use karna hai:
Now create a React frontend for the banking dispute resolution system.
 
Pages:
 
1. Customer Chat
2. Customer Dispute History
3. Dispute Details
4. Human Agent Dashboard
5. Escalation Queue
6. Analytics Dashboard
 
Customer Chat should allow:
- entering complaint
- showing classification
- asking for missing information
- showing dispute status
- showing resolution/reference number
 
Agent dashboard should show:
- dispute ID
- category
- priority
- risk
- SLA
- customer verification status
- transaction status
- recommended action
- escalation reason
 
Do not expose sensitive banking data.
Use the FastAPI backend.
PHASE 15 — Testing
Now create a comprehensive pytest test suite.
 
Test:
 
1. Database models
2. Pydantic validation
3. Mock banking tools
4. Authentication
5. Dispute classification
6. RAG retrieval
7. Rules engine
8. Risk scoring
9. LangGraph workflow
10. API endpoints
11. Escalation
12. Notifications
13. Audit logging
14. Security
 
Create:
- unit tests
- integration tests
- API tests
- workflow tests
- negative tests
- edge cases
 
Target at least 80% meaningful test coverage.
 
Do not use real banking data.
PHASE 16 — End-to-end test scenarios
Copilot ko ye zaroor dena:
Now create end-to-end test scenarios for the following cases.
 
Scenario 1:
Customer says:
"My UPI transaction failed but Rs. 500 was deducted."
 
Expected:
- classify as UPI_FAILED
- verify transaction
- retrieve policy
- evaluate rules
- low risk
- create appropriate automated resolution/request
- notify customer
- audit everything
 
Scenario 2:
"ATM did not give me cash but Rs. 10,000 was deducted."
 
Expected:
ATM dispute workflow.
 
Scenario 3:
"I don't recognize this Rs. 75,000 card transaction."
 
Expected:
- unauthorized card transaction
- high risk
- no automatic refund
- escalate to fraud/dispute team
 
Scenario 4:
"My refund has not arrived."
 
Expected:
- identify original transaction
- check refund status
- retrieve policy
- determine next action
 
Scenario 5:
Customer cannot authenticate.
 
Expected:
- do not expose transaction information
- stop workflow
- ask for appropriate verification or escalate
 
Scenario 6:
No applicable policy exists.
 
Expected:
- NO_POLICY_FOUND
- no autonomous financial action
- human escalation
 
Verify every scenario through API and LangGraph workflow.
PHASE 17 — Observability
Now add production-style observability.
 
Implement:
 
1. Structured JSON logging
2. Request IDs
3. Correlation IDs
4. LangGraph execution tracing
5. LLM latency tracking
6. Token usage tracking where supported
7. RAG retrieval metrics
8. API latency
9. Error rate
10. Dispute resolution rate
11. Escalation rate
12. Auto-resolution rate
13. Human intervention rate
 
Make the system compatible with LangSmith for LLM/LangGraph tracing.
 
Never log sensitive customer/payment information.
PHASE 18 — Docker
Now containerize the complete application.
 
Create:
 
- backend Dockerfile
- frontend Dockerfile
- docker-compose.yml
 
Services:
1. backend
2. frontend
3. PostgreSQL
4. vector database if required
 
Requirements:
- health checks
- environment variables
- persistent database volume
- persistent vector index
- non-root containers where practical
- production-style configuration
- proper startup order
- restart policies
 
The complete application must start using:
 
docker compose up --build
PHASE 19 — CI/CD
Now create GitHub Actions CI/CD.
 
Pipeline stages:
 
1. Install dependencies
2. Lint
3. Type checking
4. Unit tests
5. Integration tests
6. Security checks
7. Build Docker images
 
Fail the pipeline if tests fail.
 
Do not store secrets directly in the repository.
 
Use GitHub Secrets/environment variables for:
- LLM API key
- database credentials
- authentication secrets
- tracing keys
PHASE 20 — README
Last me Copilot ko bolo:
Now create a professional README.md for this project.
 
Include:
 
1. Project overview
2. Problem statement
3. Business use case
4. Key features
5. Architecture diagram using Mermaid
6. Technology stack
7. Project structure
8. RAG architecture
9. LangGraph workflow
10. Rules engine
11. Risk engine
12. API documentation
13. Database schema overview
14. Security
15. Human-in-the-loop escalation
16. Audit logging
17. Installation
18. Environment variables
19. Running locally
20. Running with Docker
21. Running tests
22. Example API requests
23. Example dispute scenarios
24. CI/CD
25. Monitoring
26. Limitations
27. Future enhancements
 
Clearly state that the project uses synthetic/mock banking data and is a demonstration system, not a production banking system.

Now Final- 
Perform a complete production-readiness review of this project.
 
Do not modify code initially.
 
Analyze the entire repository and identify:
 
1. Architecture issues
2. Security vulnerabilities
3. Banking safety risks
4. LLM hallucination risks
5. Prompt injection risks
6. RAG weaknesses
7. Incorrect LangGraph routing
8. Rule-engine problems
9. Database problems
10. API security problems
11. Authentication/authorization issues
12. Missing audit logs
13. Sensitive data exposure
14. Race conditions
15. Error handling problems
16. Missing tests
17. Docker issues
18. CI/CD issues
19. Performance bottlenecks
20. Observability gaps
 
For every issue provide:
- severity
- file
- problem
- why it matters
- recommended fix
 
Do not change anything until I approve the review.
Now-
implement all approved fixes one by one.
 
After each major fix:
1. run relevant tests
2. show what changed
3. verify that existing functionality still works
 
Do not remove existing functionality.
Do not bypass security controls.
Do not allow LLMs to directly execute financial actions.