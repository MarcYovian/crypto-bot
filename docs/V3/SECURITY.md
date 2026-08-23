# SECURITY.md: SMC QuantEngine

## 1. Threat Model

This section outlines potential threats, vulnerabilities, and their potential impact on the SMC QuantEngine, a high-value target due to its direct control over financial assets.

### 1.1. Key Assets
- **Financial Capital**: Funds held in the Binance exchange account.
- **Exchange API Keys**: Credentials granting programmatic access to trading and account management.
- **Trading Algorithm & Strategy Logic**: Proprietary Smart Money Concepts (SMC) implementation.
- **Database (PostgreSQL)**: Stores trade history, positions, watchlist, configuration, and potentially sensitive operational data.
- **User Credentials**: Telegram user IDs, API dashboard access tokens/keys.
- **System Configuration**: Environment variables, application settings.
- **Operational Data**: Logs, metrics, monitoring data.

### 1.2. Threat Actors
- **External Attackers**: Malicious individuals or groups attempting unauthorized access, data theft, or financial manipulation.
- **Malicious Insiders**: Authorized users (e.g., Admin) abusing privileges or developers introducing backdoors.
- **Compromised Dependencies**: Vulnerabilities in third-party libraries (e.g., `ccxt.pro`, `FastAPI`, `SQLAlchemy`).
- **State-Sponsored Actors**: Highly sophisticated attackers targeting financial infrastructure.

### 1.3. Attack Vectors & Threats
| Attack Vector | Threat | Impact | Mitigation Strategy |
|:---|:---|:---|:---|
| **Exchange API Keys** | Compromise (theft, leakage) | Unauthorized trading, fund withdrawal (if API key allows), data exfiltration. | AWS Secrets Manager, IAM roles, least privilege API key permissions (no withdrawal), regular rotation. |
| **FastAPI API Endpoints** | Unauthorized access, injection, DDoS, data tampering. | Unauthorized watchlist changes, monitoring data manipulation, service disruption. | Authentication (API Key/JWT), RBAC, input validation, rate limiting, WAF, HTTPS. |
| **Telegram Bot Interface** | Unauthorized command execution, spam, social engineering. | Emergency `close_all` abuse, status information leakage, service disruption. | Whitelisted Telegram User IDs, RBAC, input validation, rate limiting. |
| **Database (PostgreSQL)** | Unauthorized access, data injection, data exfiltration, service disruption. | Trade history alteration, position manipulation, strategy theft, system downtime. | Network isolation (VPC, Security Groups), strong credentials, least privilege, encryption at rest/in transit, regular backups. |
| **Application Codebase** | Vulnerabilities (bugs, logic flaws), supply chain attacks. | Incorrect trade execution, financial loss, data breach, system compromise. | Code reviews, static analysis, dependency scanning, unit/integration tests, secure coding practices. |
| **Cloud Infrastructure (AWS)** | Misconfiguration, unauthorized access to AWS console. | Full system compromise, data loss, resource hijacking. | IAM policies (least privilege), multi-factor authentication (MFA), infrastructure as code (IaC), regular security audits. |
| **Network Communication** | Eavesdropping, Man-in-the-Middle (MitM) attacks. | Sensitive data interception (API keys, trade data). | End-to-end encryption (HTTPS/WSS/TLS). |
| **Operational Environment** | Malware, rootkits, OS vulnerabilities. | System compromise, data theft, service disruption. | Secure base images (Docker), regular patching, host-level security. |
| **Exchange-Side Issues** | API downtime, rate limiting, market manipulation. | Missed trades, incorrect execution, financial loss. | Robust error handling (`ccxt.pro`), exponential backoff, failsafe mechanisms, monitoring. |

## 2. Authentication and Authorization Design

The SMC QuantEngine implements a multi-layered approach to authentication and authorization, tailored to its distinct interfaces.

### 2.1. FastAPI Web Dashboard API
-   **Authentication**:
    -   **API Key Authentication**: For programmatic access (e.g., by a frontend dashboard application), a secure API key mechanism will be used. API keys are generated securely, stored hashed in the database, and transmitted via `Authorization: Bearer <API_KEY>` header.
    -   **JWT (JSON Web Token) Authentication**: For interactive user sessions (if a future frontend requires login), JWTs will be issued upon successful authentication (e.g., username/password, though not in initial scope). JWTs will be short-lived and refreshed securely.
-   **Authorization (Role-Based Access Control - RBAC)**:
    -   **Roles**: `Admin`, `Trader`.
    -   **Permissions**:
        -   `Admin`: Full control over all API endpoints, including `/v1/watchlist` (add/remove symbols), `/v1/config` (if implemented), and `/v1/overview`. Can trigger emergency actions.
        -   `Trader`: Read-only access to `/v1/overview` and `/v1/positions`. Can initiate specific trade overrides (e.g., close position) if explicitly enabled and audited.
    -   **Implementation**: FastAPI dependencies will validate the authenticated user's role against the required permissions for each endpoint.

### 2.2. Telegram Bot Interface
-   **Authentication**:
    -   **Whitelisted User IDs**: The Telegram bot will only respond to commands from a predefined list of authorized Telegram User IDs. This list will be stored securely (e.g., in the database or configuration, managed via AWS Secrets Manager).
    -   **No Password/API Key**: Telegram's built-in security (user ID) is leveraged.
-   **Authorization (Role-Based Access Control - RBAC)**:
    -   **Roles**: `Admin`, `Trader`.
    -   **Permissions**:
        -   `Admin`: Can execute all commands, including `/close_all`, `/status`, and potentially future configuration commands.
        -   `Trader`: Can execute `/status` and other read-only commands. Cannot execute `/close_all`.
    -   **Implementation**: The Telegram bot handler will check the sender's User ID against the authorized list and their assigned role before processing any command.

### 2.3. Internal Service-to-Service / Database Access
-   **Database Access**:
    -   Dedicated PostgreSQL user accounts with strong, unique passwords for the application (FastAPI, workers).
    -   **Least Privilege**: Database users will only have permissions necessary for their function (e.g., `SELECT`, `INSERT`, `UPDATE`, `DELETE` on specific tables). No `SUPERUSER` or `ALL PRIVILEGES` for application users.
    -   Credentials managed via AWS Secrets Manager.
-   **Inter-Service Communication**:
    -   Within the `backend` application, direct function calls are used.
    -   If the architecture evolves into separate microservices, secure inter-service communication (e.g., mTLS, signed requests) would be implemented.

## 3. Data Encryption

Ensuring the confidentiality and integrity of data, both in transit and at rest, is paramount for a financial trading platform.

### 3.1. Data in Transit
-   **External APIs (Binance, Telegram)**: All communication with Binance (REST and WebSockets via `ccxt.pro`) and Telegram APIs will utilize **TLS 1.2+ (HTTPS/WSS)**. This encrypts data between the SMC QuantEngine and the respective external services, preventing eavesdropping and tampering.
-   **FastAPI Web API**: All client-server communication with the FastAPI dashboard API will be enforced over **HTTPS (TLS 1.2+)**. This will be handled by a Load Balancer (e.g., AWS ALB) configured to terminate TLS and redirect HTTP traffic.
-   **Database Connections**: Connections between the application components (FastAPI, workers) and the PostgreSQL database will be encrypted using **SSL/TLS**. This is a standard feature of `asyncpg` and PostgreSQL, ensuring secure communication within the private network.
-   **Internal AWS Services**: Communication with AWS Secrets Manager, CloudWatch, etc., will leverage AWS's internal secure communication channels, which are encrypted by default.

### 3.2. Data at Rest
-   **Database (PostgreSQL)**: The PostgreSQL database will be deployed on a managed service (e.g., AWS RDS) with **disk encryption enabled (e.g., AWS EBS encryption)**. This ensures that all data stored on the database's underlying storage volumes is encrypted.
-   **Secrets Management (AWS Secrets Manager)**: All sensitive credentials (Binance API keys, Telegram bot token, DB credentials) are stored in AWS Secrets Manager, which inherently encrypts secrets at rest using AWS Key Management Service (KMS).
-   **Logs and Metrics**: Log data (e.g., in AWS CloudWatch Logs or Loki) and metrics data (e.g., in Prometheus storage) will be stored in encrypted storage solutions provided by the cloud provider.
-   **Backups**: All database backups and snapshots will also be encrypted at rest.

## 4. Secrets Management

Secure handling of sensitive credentials is a critical security pillar for the SMC QuantEngine.

### 4.1. AWS Secrets Manager
-   **Centralized Storage**: All sensitive credentials, including Binance API keys (read-only for trading, no withdrawal permissions), Telegram bot token, and PostgreSQL database credentials, will be stored exclusively in **AWS Secrets Manager**.
-   **No Hardcoding**: Secrets will never be hardcoded in the application's source code, configuration files, or environment variables directly.
-   **Runtime Retrieval**: The application components will retrieve secrets from AWS Secrets Manager at runtime using appropriate AWS SDKs.
-   **Least Privilege Access**: IAM roles attached to the ECS tasks (running FastAPI, workers) will be granted only the minimum necessary permissions to `GetSecretValue` for the specific secrets they require.
-   **Automatic Rotation**: Where feasible and supported by AWS Secrets Manager, automatic rotation of secrets (e.g., database credentials) will be configured to enhance security posture.
-   **Versioning**: Secrets Manager maintains versions of secrets, allowing for rollback if a new secret causes issues.

## 5. Network Security

The network architecture is designed to isolate components and restrict access, minimizing the attack surface.

### 5.1. Virtual Private Cloud (VPC)
-   The entire SMC QuantEngine infrastructure will be deployed within a dedicated **AWS Virtual Private Cloud (VPC)**, providing a logically isolated network.
-   Components will reside in private subnets, with no direct public internet access unless explicitly required and secured.

### 5.2. Security Groups
-   **Database Security Group**:
    -   Ingress: Only allows traffic from the Security Groups associated with the application servers (FastAPI, workers).
    -   Egress: Restricted to necessary outbound connections (e.g., to AWS KMS for encryption).
    -   **Crucially, no direct public internet access to the database.**
-   **Application Server Security Group (FastAPI, Workers)**:
    -   **FastAPI**: Ingress from the Load Balancer's Security Group (for HTTP/HTTPS traffic).
    -   **Workers**: No public ingress.
    -   Egress: Allowed to Binance API endpoints (specific IP ranges if possible, or `0.0.0.0/0` for HTTPS), Telegram API, AWS Secrets Manager, CloudWatch, and PostgreSQL database.
-   **Load Balancer Security Group**:
    -   Ingress: Allows HTTP (port 80) and HTTPS (port 443) traffic from the internet (`0.0.0.0/0`).
    -   Egress: To the FastAPI application servers.

### 5.3. Network Access Control Lists (NACLs)
-   NACLs will be configured at the subnet level to provide an additional, stateless layer of network security, complementing Security Groups.

### 5.4. Web Application Firewall (WAF)
-   An AWS WAF can be deployed in front of the Load Balancer to protect the FastAPI API from common web exploits and bots, including SQL injection and cross-site scripting (XSS) attempts.

## 6. OWASP Top 10 Mitigations (FastAPI API)

While the FastAPI API is primarily for internal dashboard integration, it still requires robust security measures.

### 6.1. A01:2021-Broken Access Control
-   **Mitigation**: Implement robust Role-Based Access Control (RBAC) as detailed in Section 2.1, ensuring that only authorized users with the correct roles can access specific API endpoints and perform actions. FastAPI dependencies will enforce these checks.

### 6.2. A02:2021-Cryptographic Failures (Sensitive Data Exposure)
-   **Mitigation**:
    -   All sensitive data (API keys, trade data) is encrypted in transit (HTTPS/WSS/TLS) and at rest (disk encryption, Secrets Manager).
    -   Avoid logging sensitive information directly.
    -   Use secure, industry-standard cryptographic algorithms.

### 6.3. A03:2021-Injection
-   **Mitigation**:
    -   **SQL Injection**: Utilize SQLAlchemy ORM for all database interactions. This inherently uses parameterized queries, preventing SQL injection.
    -   **Command Injection**: Avoid executing external commands with user-supplied input. If necessary, sanitize and validate all input rigorously.
    -   **Input Validation**: FastAPI's Pydantic models provide strong data validation for all incoming API requests, preventing malformed or malicious input from reaching the application logic.

### 6.4. A04:2021-Insecure Design
-   **Mitigation**:
    -   Adhere to the Hexagonal Architecture and Clean Architecture principles, promoting modularity and clear separation of concerns, which aids in identifying and isolating security flaws.
    -   Implement a comprehensive threat model (Section 1) early in the design phase.
    -   Design for least privilege in all components (IAM roles, database users, API key permissions).

### 6.5. A05:2021-Security Misconfiguration
-   **Mitigation**:
    -   **Infrastructure as Code (IaC)**: Use tools like AWS CloudFormation or Terraform to define and manage infrastructure, ensuring consistent and secure configurations.
    -   **Secure Defaults**: Configure all services (PostgreSQL, Load Balancers, ECS) with security best practices in mind (e.g., disable unnecessary features, strong ciphers).
    -   **Regular Audits**: Periodically review cloud configurations and application settings for misconfigurations.

### 6.6. A07:2021-Identification and Authentication Failures
-   **Mitigation**:
    -   Implement secure API key/JWT authentication with proper validation, storage (hashed API keys), and transmission (HTTPS).
    -   Enforce strong API key policies (e.g., length, complexity, rotation).
    -   Implement rate limiting on authentication attempts to prevent brute-force attacks.

### 6.7. A09:2021-Security Logging and Monitoring Failures
-   **Mitigation**:
    -   **Comprehensive Logging**: Log all security-relevant events, including authentication attempts (success/failure), authorization failures, critical system errors, and trade execution events.
    -   **Centralized Logging**: Aggregate logs to a centralized system (e.g., AWS CloudWatch Logs, Loki) for easy analysis and retention.
    -   **Alerting**: Configure alerts for suspicious activities (e.g., repeated failed login attempts, unauthorized access attempts, critical system failures, API key usage anomalies).
    -   **Monitoring**: Utilize Prometheus and Grafana for real-time monitoring of system health, performance, and security metrics.

## 7. Compliance and Auditing

While no specific regulatory compliance (e.g., FINRA, MiFID II) is explicitly required for this project, adherence to general best practices for financial systems is crucial.

### 7.1. Data Integrity and Confidentiality
-   Ensure that all data related to trading (positions, orders, PnL) maintains its integrity and confidentiality through encryption, access controls, and validation.
-   Implement robust error handling and data reconciliation mechanisms to prevent data corruption.

### 7.2. Audit Trails
-   Maintain detailed, immutable audit trails for all critical actions:
    -   API key usage.
    -   Telegram command executions (especially `/close_all`).
    -   Watchlist modifications.
    -   Trade signal generation and execution.
    -   System configuration changes.
-   Logs will include timestamps, user/system identifiers, and the action performed.

### 7.3. Regular Security Reviews
-   Conduct periodic internal security reviews of the codebase, infrastructure, and operational procedures.
-   Perform dependency vulnerability scanning to identify and address known vulnerabilities in third-party libraries.

## 8. Penetration Testing Scope

A comprehensive penetration test will be conducted to identify vulnerabilities before production deployment.

### 8.1. External Attack Surface
-   **FastAPI Web API**: All exposed `/v1/*` endpoints will be tested for:
    -   Authentication bypass.
    -   Authorization flaws (privilege escalation).
    -   Injection vulnerabilities (SQL, command).
    -   Broken access control.
    -   Rate limiting bypass.
    -   Denial of Service (DoS) vectors.
    -   Sensitive data exposure.
-   **Telegram Bot Interface**:
    -   Unauthorized command execution.
    -   Input validation bypass.
    -   Rate limiting and DoS.
    -   Information leakage.

### 8.2. Internal Attack Surface (Simulated)
-   **Cloud Infrastructure**:
    -   AWS IAM roles and policies.
    -   Security Group and NACL configurations.
    -   AWS Secrets Manager access controls.
    -   S3 bucket policies (if used for logs/backups).
    -   RDS database security.
-   **Application Logic**:
    -   Testing the core trading logic for potential manipulation or unintended behavior (e.g., forcing incorrect position sizing, bypassing risk management rules).
    -   Verification of state synchronization mechanisms between the bot, database, and exchange.
    -   Failsafe mechanism effectiveness.

### 8.3. Data Security
-   Verification of data encryption at rest and in transit.
-   Testing for unauthorized data access or modification within the database.

### 8.4. Supply Chain Security
-   Review of third-party dependencies for known vulnerabilities.

### 8.5. Operational Security
-   Review of logging, monitoring, and alerting configurations for effectiveness.
-   Incident response plan review.