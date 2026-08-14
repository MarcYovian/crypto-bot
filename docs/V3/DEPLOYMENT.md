# DEPLOYMENT.md: SMC QuantEngine

This document outlines the deployment strategy, CI/CD pipeline, environment configuration, monitoring, and rollback procedures for the SMC QuantEngine. The goal is to establish a robust, automated, and observable deployment process for this advanced algorithmic trading platform.

## 1. CI/CD Pipeline

The Continuous Integration/Continuous Deployment (CI/CD) pipeline automates the process of building, testing, and deploying the SMC QuantEngine application. This ensures rapid, reliable, and consistent deployments across all environments.

### 1.1. Pipeline Stages

The pipeline is typically orchestrated using a tool like GitHub Actions, GitLab CI/CD, or AWS CodePipeline. The general stages are as follows:

1.  **Source Code Checkout**:
    *   **Trigger**: Git push to `main` (for production) or `develop` (for staging/dev) branches, or pull request merge.
    *   **Action**: Clones the repository.
2.  **Linting & Static Analysis**:
    *   **Tools**: `flake8`, `mypy`, `black`, `isort`.
    *   **Action**: Checks code quality, style adherence, and type correctness. Fails if issues are found.
3.  **Unit & Integration Tests**:
    *   **Tools**: `pytest`, `pytest-asyncio`.
    *   **Action**: Runs all defined unit and integration tests. Requires a temporary test database instance or mocks for external services. Fails if tests do not pass.
4.  **Docker Image Build**:
    *   **Action**: Builds the Docker image for the application using the `Dockerfile` located in the `backend/` directory. A multi-stage build is used to minimize image size and improve security.
    *   **Tagging**: Images are tagged with a unique identifier (e.g., Git commit SHA, build number, or semantic version).
5.  **Image Scan (Optional but Recommended)**:
    *   **Tools**: AWS ECR Image Scanning, Clair, Trivy.
    *   **Action**: Scans the built Docker image for known vulnerabilities. Fails if critical vulnerabilities are detected.
6.  **Push to Container Registry**:
    *   **Target**: AWS Elastic Container Registry (ECR).
    *   **Action**: Pushes the tagged Docker image to the designated ECR repository (e.g., `smc-quantengine-repo`).
7.  **Deployment to Environment**:
    *   **Target**: AWS Elastic Container Service (ECS) on Fargate.
    *   **Action**: Updates the ECS Service with the new Docker image tag. This triggers a rolling update, replacing old tasks with new ones.
    *   **Environment-Specific Configuration**: Environment variables and secrets are injected at this stage based on the target environment (Dev, Staging, Production).
8.  **Post-Deployment Smoke Tests**:
    *   **Action**: After deployment, runs basic health checks and API endpoint tests (e.g., `GET /v1/health`, `GET /v1/overview`) to ensure the application is running and responsive.

## 2. Environment Strategy

A multi-environment strategy is employed to ensure proper testing, isolation, and risk management before deploying to production.

| Environment | Purpose | Access | Data | Scale | Deployment Trigger |
|:------------|:--------|:-------|:-----|:------|:-------------------|
| **Development** | Local development, feature branch testing. | Developers only | Local/Ephemeral DB | Minimal | Local build/run |
| **Staging** | Pre-production testing, integration testing, UAT. | Devs, QA, Stakeholders | Near-production data (sanitized) | Production-like | Merge to `develop` branch |
| **Production** | Live trading operations. | Restricted (Ops/Admin) | Live trading data | Full | Merge to `main` branch |

### 2.1. Environment Configuration

*   **Isolation**: Each environment (Staging, Production) runs in its own dedicated AWS VPC or separate subnets within a VPC, with distinct ECS clusters, RDS instances, and Secrets Manager configurations.
*   **Secrets Management**: All sensitive configurations (API keys, database credentials, Telegram bot tokens) are stored in AWS Secrets Manager, with environment-specific secret names.
*   **Configuration**: Non-sensitive configurations (e.g., log levels, feature flags) are managed via environment variables injected into ECS Task Definitions.
*   **Database**: Each environment has its own PostgreSQL database instance (AWS RDS), ensuring data isolation.

## 3. Containerization (Docker)

The SMC QuantEngine application is containerized using Docker to ensure consistency across development, testing, and production environments.

### 3.1. Dockerfile Structure

A multi-stage `Dockerfile` is used to create optimized production images.

```dockerfile
# Stage 1: Builder - Install dependencies
FROM python:3.10-slim-buster AS builder

WORKDIR /app

# Install system dependencies for psycopg2 and pandas
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Stage 2: Production - Copy only necessary files
FROM python:3.10-slim-buster AS production

WORKDIR /app

# Install system dependencies for psycopg2 (runtime only)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder stage
COPY --from=builder /usr/local/lib/python3.10/site-packages /usr/local/lib/python3.10/site-packages
COPY --from=builder /usr/local/bin/uvicorn /usr/local/bin/uvicorn

# Copy application code
COPY backend/ .

# Expose the port for FastAPI
EXPOSE 8000

# Define entry points for different services
# Default command (e.g., for API service)
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 3.2. Entry Points for Services

The single Docker image can serve multiple roles (API, Telegram Bot, Worker) by specifying different `command` overrides in the ECS Task Definition:

*   **API Service**: `uvicorn src.api.main:app --host 0.0.0.0 --port 8000`
*   **Telegram Bot Service**: `python -m src.bot.main`
*   **Worker Service**: `python -m src.worker.main`

## 4. Serverless Container Orchestration (AWS ECS on Fargate)

The SMC QuantEngine is deployed on AWS Elastic Container Service (ECS) using the Fargate launch type. This provides a serverless operational model, abstracting away server management and enabling automatic scaling and high availability.

### 4.1. AWS Services Utilized

*   **Amazon ECS**: Orchestrates Docker containers.
    *   **Cluster**: A logical grouping of ECS services.
    *   **Task Definition**: A blueprint for running containers, specifying image, CPU/memory, environment variables, and secrets.
    *   **Service**: Maintains a desired number of tasks, handles load balancing, and auto-scaling.
    *   **Fargate Launch Type**: Runs containers without managing EC2 instances.
*   **Amazon RDS for PostgreSQL**: Managed relational database service.
*   **AWS Secrets Manager**: Secure storage and retrieval of sensitive credentials.
*   **Amazon VPC**: Isolated network environment.
*   **AWS CloudWatch**: Centralized logging and monitoring.
*   **AWS Application Load Balancer (ALB)**: Distributes incoming API traffic (for FastAPI service).
*   **AWS IAM**: Manages access control and permissions.

### 4.2. Network Architecture

*   **VPC**: A dedicated Virtual Private Cloud (VPC) is provisioned for the application.
*   **Subnets**:
    *   **Public Subnets**: For the Application Load Balancer (ALB) if the FastAPI service needs public access.
    *   **Private Subnets**: For all ECS Fargate tasks (API, Bot, Worker) and the RDS PostgreSQL instance. This ensures that application components and the database are not directly accessible from the public internet.
*   **NAT Gateway**: Deployed in public subnets to allow Fargate tasks in private subnets to access external services (e.g., Binance API, Telegram API) for outbound connections.
*   **Security Groups**: Granular network access control:
    *   ALB Security Group: Allows inbound traffic on port 80/443 from the internet.
    *   ECS Fargate Security Group: Allows inbound traffic from the ALB (for API service) and outbound traffic to RDS and NAT Gateway.
    *   RDS Security Group: Allows inbound traffic only from the ECS Fargate Security Group on the PostgreSQL port (5432).

### 4.3. ECS Service Configuration

Each logical component (API, Telegram Bot, Worker) is deployed as a separate ECS Service within the same cluster:

*   **`quantengine-api-service`**:
    *   **Task Definition**: Specifies the Docker image, CPU/Memory (e.g., 1 vCPU, 2GB RAM), environment variables, and secrets.
    *   **Container Port**: 8000 (for Uvicorn).
    *   **Load Balancer**: Associated with an ALB to expose the FastAPI endpoints.
    *   **Auto-Scaling**: Configured to scale based on CPU utilization or request count.
*   **`quantengine-bot-service`**:
    *   **Task Definition**: Similar to API, but with `command` overridden to run the Telegram bot entry point.
    *   **Network**: No public exposure; relies on outbound connections to Telegram API.
    *   **Scaling**: Typically runs as a single task or a small fixed number of tasks.
*   **`quantengine-worker-service`**:
    *   **Task Definition**: Similar to API, with `command` overridden to run the worker entry point.
    *   **Network**: No public exposure; relies on outbound connections to Binance WebSockets/REST API.
    *   **Scaling**: Can be scaled based on workload (e.g., number of symbols in watchlist) or run as a fixed number of tasks.

### 4.4. Database Deployment (AWS RDS PostgreSQL)

*   **Instance Type**: Chosen based on performance and scaling requirements (e.g., `db.t3.medium` for staging, `db.m5.large` for production).
*   **Multi-AZ Deployment**: Enabled for high availability and automatic failover.
*   **Storage**: Provisioned IOPS SSD for consistent performance.
*   **Backups**: Automated daily snapshots with a retention period.
*   **Connection**: Application connects using credentials retrieved from AWS Secrets Manager.

### 4.5. Secrets Management (AWS Secrets Manager)

*   All sensitive data (Binance API keys, Telegram bot token, database credentials, etc.) are stored as secrets in AWS Secrets Manager.
*   ECS Task Definitions are configured to inject these secrets directly as environment variables into the running containers, ensuring they are never hardcoded or exposed in plain text.
*   IAM roles are used to grant ECS tasks permission to retrieve specific secrets.

## 5. Monitoring & Logging

Comprehensive monitoring and logging are critical for the operational health and performance of the SMC QuantEngine.

### 5.1. Logging (Loki + Grafana)

*   **Container Logs**: All application logs from Docker containers are sent to AWS CloudWatch Logs using the `awslogs` driver in the ECS Task Definition.
*   **Log Aggregation**: AWS CloudWatch Logs are then scraped by a Loki instance (potentially deployed on a separate ECS service or EC2 instance) for centralized log aggregation.
*   **Structured Logging**: The Python application uses structured logging (e.g., `jsonlogger`) to output logs in JSON format, making them easily queryable in Loki.
*   **Visualization**: Grafana is used to query, filter, and visualize logs from Loki, enabling quick debugging and operational insights.

### 5.2. Metrics (Prometheus + Grafana)

*   **Application Metrics**: The Python application exposes custom metrics (e.g., trade count, PnL, latency, error rates, active positions) using the `prometheus_client` library.
*   **System Metrics**: ECS provides built-in metrics for CPU, memory, and network utilization.
*   **Prometheus**: A Prometheus server (deployed on a dedicated ECS service or EC2 instance) scrapes metrics from:
    *   The FastAPI service (`/metrics` endpoint).
    *   The Telegram Bot and Worker services (if they expose metrics).
    *   ECS service discovery is used to automatically find and scrape targets.
*   **Visualization & Alerting**: Grafana dashboards display key performance indicators (KPIs) and operational metrics. Alerts are configured in Grafana (or Prometheus Alertmanager) to notify operators via PagerDuty, Slack, or email for critical events (e.g., high error rates, low equity, service downtime).

### 5.3. Health Checks

*   **FastAPI**: Exposes a `/v1/health` endpoint for basic service health checks by the ALB.
*   **ECS Task Health Checks**: Configured in Task Definitions to monitor the health of individual containers. If a container fails health checks, ECS will automatically restart it.
*   **Database Health**: RDS provides metrics for database health, connections, and performance.

## 6. Rollback Procedures

In the event of a critical issue, a rapid and reliable rollback mechanism is essential to minimize downtime and potential financial impact.

### 6.1. Application Rollback

*   **ECS Service Update**: If a new deployment introduces a bug, the ECS Service can be updated to revert to a previous, stable Task Definition revision. This triggers a rolling update, replacing the problematic tasks with the last known good version.
*   **CI/CD Pipeline**: The CI/CD pipeline retains previous Docker image tags in ECR, allowing for easy selection of an older version for rollback.

### 6.2. Database Rollback

*   **RDS Snapshots**: AWS RDS automatically creates daily snapshots of the database. In a catastrophic data corruption scenario, the database can be restored to a previous point in time from these snapshots.
*   **Point-in-Time Recovery**: RDS also supports point-in-time recovery, allowing restoration to any specific second within the backup retention period.
*   **Schema Migrations**: Database schema changes are managed using tools like Alembic. Rollback of schema changes requires careful planning and potentially reverse migrations.

### 6.3. Emergency Failsafe

As per FR-13, the system implements a master failsafe mechanism:
*   Upon critical, unrecoverable errors (e.g., repeated authentication failures with Binance, prolonged database connection loss), the application will:
    1.  **Pause Operations**: Stop all market scanning, signal generation, and trade execution.
    2.  **Alert**: Dispatch a high-priority alert via Telegram and other monitoring channels (e.g., PagerDuty).
    3.  **State**: Enter a "paused" state, awaiting manual intervention or resolution of the underlying issue. This state is reflected in monitoring dashboards.

## 7. Configuration Management

Configuration for the SMC QuantEngine is managed through a combination of environment variables and AWS Secrets Manager.

*   **Environment Variables**: Used for non-sensitive, environment-specific settings (e.g., `APP_ENV=production`, `LOG_LEVEL=INFO`, `WATCHLIST_REFRESH_INTERVAL_SECONDS=300`). These are defined in the ECS Task Definitions.
*   **AWS Secrets Manager**: Used for all sensitive credentials and API keys (e.g., `BINANCE_API_KEY`, `BINANCE_SECRET_KEY`, `TELEGRAM_BOT_TOKEN`, `DATABASE_URL`). Secrets are injected into containers at runtime, never committed to source control.
*   **Parameter Store (Optional)**: For less sensitive but frequently changing parameters that don't warrant Secrets Manager's overhead, AWS Systems Manager Parameter Store could be used.

This deployment strategy ensures that the SMC QuantEngine is not only performant and reliable but also secure and maintainable in a production trading environment.