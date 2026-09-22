# DevinBot - Custom Devin API Integration Platform

## Project Overview

DevinBot is a custom backend application that integrates with Devin's API to automate software development workflows for a one-man developer. It provides GitHub webhook integration, Telegram-based control and monitoring, scheduled task execution, and real-time observability through a mobile web dashboard.

## Core Use Cases

1. **Pull Request Review**: Automatically trigger Devin to review PRs when they are raised on GitHub repositories
2. **Issue-based Development**: Automatically start Devin sessions to work on code when GitHub issues are created
3. **Scheduled Tasks**: Create and manage scheduled tasks that run Devin sessions with custom prompts
4. **Telegram Control**: Two-way Telegram integration for monitoring job status and controlling Devin sessions
5. **Real-time Observability**: Mobile web dashboard showing success rates, session counts, cost consumption, and active/completed sessions

## Architecture

### High-Level Components

```
GitHub Webhooks → FastAPI Backend → Devin API
                                        ↓
Telegram Bot ← FastAPI Backend ← Devin Sessions/Sessions/Metrics
                                        ↓
                                  Next.js Mobile Dashboard
```

### Backend (Python/FastAPI)

**Main Components:**
- `webhook_receiver.py` - GitHub webhook handler for PRs and issues
- `devin_client.py` - Devin API client wrapper (sessions, PR reviews, metrics)
- `telegram_bot.py` - Telegram bot with two-way communication
- `scheduler.py` - Scheduled task management using APScheduler
- `observability.py` - Real-time metrics fetching from Devin Analytics API
- `database.py` - PostgreSQL for job tracking, repository configuration, and user state

**API Endpoints:**
- `POST /webhooks/github` - GitHub webhook receiver
- `POST /webhooks/telegram` - Telegram webhook receiver
- `GET /api/sessions` - List active/completed sessions
- `POST /api/sessions` - Create new Devin session
- `POST /api/sessions/{id}/cancel` - Cancel running session
- `GET /api/metrics` - Real-time observability metrics
- `POST /api/scheduled-tasks` - Create scheduled task
- `GET /api/repositories` - List configured repositories

### Frontend (Next.js Mobile Web App)

**Components:**
- `Dashboard` - Main mobile-optimized dashboard
- `SessionList` - Active vs completed sessions view
- `MetricsCard` - Success rates, cost consumption, session counts
- `RepositorySelector` - Multi-repository selection
- `RealTimeUpdates` - WebSocket or polling for real-time data

**Mobile-First Design:**
- Responsive layout optimized for mobile screens
- Touch-friendly interface
- Bottom navigation for key metrics
- Swipe gestures for session management

### Devin API Integration

**Key Endpoints Used:**
- `POST /v3/organizations/{org_id}/sessions` - Create sessions
- `GET /v3/organizations/{org_id}/sessions` - List sessions
- `GET /v3/organizations/{org_id}/sessions/{id}` - Get session details
- `DELETE /v3/organizations/{org_id}/sessions/{id}` - Terminate sessions
- `POST /v3/organizations/{org_id}/pr-reviews` - Trigger PR reviews
- `GET /v3/organizations/{org_id}/metrics/usage` - Usage metrics
- `GET /v3/organizations/{org_id}/consumption/daily` - Daily ACU consumption

### Telegram Integration Strategy

**Two-Way Communication:**
- **Notifications → Telegram**: Devin session status updates, completion notifications, error alerts
- **Commands → Backend**: Telegram commands to control sessions and query status

**Chat Topic Organization:**
- Each GitHub repository maps to a specific Telegram chat topic
- Repository configuration stored in database with topic mapping
- Messages routed to appropriate topic based on repository context

**Telegram Commands:**
- `/status` - Show active sessions for current repo topic
- `/cancel <session_id>` - Cancel a running session
- `/create <prompt>` - Create new session with custom prompt
- `/metrics` - Show current metrics for repository
- `/help` - List available commands

### GitHub Webhook Handling

**PR Events:**
- `pull_request` (opened, synchronized) → Trigger Devin session or PR review
- Extract PR URL, branch, commit details
- Create Devin session with repository context and PR review prompt

**Issue Events:**
- `issues` (opened, labeled) → Trigger Devin session for issue resolution
- Extract issue title, body, labels
- Create Devin session with issue context and development prompt

**Webhook Security:**
- Verify GitHub webhook signatures using HMAC-SHA256
- Store GitHub webhook secrets in environment variables
- Reject invalid signatures with 401 response

### Multi-Repository Support

**Database Schema:**
```sql
repositories:
  - id (UUID, primary key)
  - github_repo_path (e.g., "owner/repo")
  - telegram_chat_id (for topic mapping)
  - telegram_topic_id (optional, for topics)
  - devin_org_id (Devin organization ID)
  - webhook_secret (GitHub webhook secret)
  - created_at, updated_at

sessions:
  - id (UUID, primary key)
  - devin_session_id (Devin session ID)
  - repository_id (foreign key)
  - trigger_type (pr_review, issue, scheduled, manual)
  - trigger_context (JSON with PR/issue details)
  - status (pending, running, completed, failed, cancelled)
  - prompt (used prompt)
  - created_at, updated_at, completed_at

scheduled_tasks:
  - id (UUID, primary key)
  - repository_id (foreign key)
  - cron_expression (APScheduler format)
  - prompt (task prompt)
  - devin_mode (normal, fast, lite, ultra, fusion)
  - enabled (boolean)
  - last_run_at, next_run_at
```

### Scheduled Task Management

**Using APScheduler:**
- Python-based scheduler with cron-like expressions
- Persistent job storage in database
- Support for one-time and recurring tasks
- Automatic retry on failure

**Task Configuration:**
- Repository-specific scheduled tasks
- Custom prompts per task
- Devin mode selection (normal, fast, lite, ultra, fusion)
- Enable/disable functionality

### Real-Time Observability

**Metrics Sources:**
1. **Devin Usage Metrics API** (`/v3/organizations/{org_id}/metrics/usage`)
   - Session counts, active vs completed
   - Time-range filtering capabilities

2. **Devin Consumption API** (`/v3/organizations/{org_id}/consumption/daily`)
   - Daily ACU consumption (Enterprise plans only)
   - Daily aggregated data (midnight PST boundaries)
   - Flexible filtering and grouping

3. **Session Status Tracking** (local database)
   - Real-time session status updates
   - Success rate calculations
   - Per-repository metrics

**Real-Time Updates:**
- WebSocket connection from Next.js dashboard to FastAPI backend
- Push-based updates when session status changes
- Fallback to polling (30-second intervals) if WebSocket unavailable

**Dashboard Metrics:**
- **Success Rate**: (completed sessions / total sessions) × 100
- **Active Sessions**: Count of sessions with status 'running'
- **Completed Sessions**: Count of sessions with status 'completed'
- **Cost Consumption**: Total ACUs from the consumption API
- **Session Count**: Total sessions per time period (day, week, month)

## Development Approach

### Phase 1: Core Backend Infrastructure
1. Set up FastAPI project structure with proper dependencies
2. Implement database schema and migrations (Alembic)
3. Create Devin API client wrapper with authentication
4. Implement GitHub webhook receiver with signature verification
5. Set up basic Telegram bot with command handling

### Phase 2: Devin Integration
1. Implement session creation with repository context
2. Add PR review triggering via Devin API
3. Implement session status polling and updates
4. Add session cancellation functionality
5. Test end-to-end GitHub webhook → Devin session flow

### Phase 3: Telegram Features
1. Implement repository-to-Telegram topic mapping
2. Add session status notifications to Telegram
3. Implement Telegram commands for session control
4. Add error handling and retry logic for Telegram API
5. Test two-way communication flow

### Phase 4: Scheduling
1. Integrate APScheduler for task scheduling
2. Implement scheduled task CRUD operations
3. Add database persistence for scheduled tasks
4. Implement scheduled task execution with Devin API
5. Add scheduling UI controls (optional)

### Phase 5: Observability Dashboard
1. Set up Next.js project with mobile-first design
2. Implement FastAPI WebSocket endpoint for real-time updates
3. Create dashboard components for metrics display
4. Integrate Devin Analytics API for cost data
5. Add repository selector and filtering
6. Implement real-time updates via WebSocket/polling

### Phase 6: Testing & Deployment
1. Add comprehensive unit tests for core components
2. Implement integration tests for webhook flows
3. Add error handling and logging throughout
4. Set up environment configuration management
5. Create deployment documentation

## Technology Stack

### Backend
- **Framework**: FastAPI (Python 3.11+)
- **Database**: PostgreSQL with SQLAlchemy ORM
- **Task Scheduling**: APScheduler
- **HTTP Client**: httpx for async Devin API calls
- **Telegram**: python-telegram-bot library
- **WebSockets**: FastAPI WebSocket support
- **Environment**: python-dotenv for configuration

### Frontend
- **Framework**: Next.js 14+ with App Router
- **Styling**: Tailwind CSS for mobile-first design
- **Real-time**: Native WebSocket client or SWR for polling
- **Charts**: Recharts or Chart.js for metrics visualization
- **State Management**: React Context or Zustand

### DevOps
- **Containerization**: Docker for both backend and frontend
- **Process Management**: systemd or Docker Compose
- **Reverse Proxy**: Nginx for production deployment
- **SSL**: Let's Encrypt for HTTPS

## Configuration Required

### Environment Variables
```bash
# Devin API
DEVIN_API_KEY=cog_xxxxxxxxxxxx
DEVIN_ORG_ID=org-xxxxxxxxxxxxx

# GitHub
GITHUB_WEBHOOK_SECRET=your_webhook_secret
GITHUB_TOKEN=your_personal_access_token

# Telegram
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_main_chat_id

# Database
DATABASE_URL=postgresql://user:password@localhost/devinbot

# Application
APP_BASE_URL=https://your-domain.com
LOG_LEVEL=INFO
```

### Devin Service User Permissions
- `UseDevinSessions` - Create and manage sessions
- `ImpersonateOrgSessions` - Create sessions on behalf of users (if needed)
- `UseReviewManual` - Trigger PR reviews
- `ViewOrgMetrics` - Access usage metrics
- `ViewOrgConsumption` - Access daily ACU consumption

## Security Considerations

1. **Webhook Verification**: Always verify GitHub webhook signatures
2. **API Key Security**: Store Devin API keys in environment variables, never commit to git
3. **Telegram Security**: Validate chat IDs and implement access control
4. **Rate Limiting**: Implement rate limiting for public endpoints
5. **Input Validation**: Validate all user inputs and webhook payloads
6. **Database Security**: Use parameterized queries, never string concatenation
7. **HTTPS Only**: Force HTTPS in production for all communications

## Error Handling Strategy

1. **Webhook Errors**: Return appropriate HTTP status codes, log errors, retry on transient failures
2. **Devin API Errors**: Implement exponential backoff, handle rate limits (429), log detailed errors
3. **Telegram Errors**: Implement retry logic for failed message sends, log delivery failures
4. **Database Errors**: Use transactions, implement connection pooling, handle connection failures
5. **Scheduler Errors**: Log task failures, implement retry logic, alert on repeated failures

## Logging & Monitoring

1. **Structured Logging**: Use JSON-formatted logs with correlation IDs
2. **Log Levels**: DEBUG for development, INFO for production, ERROR for failures
3. **Key Events**: Webhook receipts, session creation, status changes, errors
4. **Metrics**: Track API call counts, response times, error rates
5. **Alerts**: Alert on repeated failures, high error rates, service unavailability

## Development Guidelines for Coding Agents

1. **Start with database schema**: Implement the core data model first
2. **Test Devin API integration**: Verify API credentials and permissions before building complex flows
3. **Implement webhook security early**: Don't skip signature verification
4. **Use async/await consistently**: FastAPI and httpx work best with async patterns
5. **Modular design**: Keep components loosely coupled for easier testing and maintenance
6. **Error-first thinking**: Handle errors at each integration point before happy path
7. **Mobile-first frontend**: Design for mobile screens from the start, not as an afterthought
8. **Real-time considerations**: Plan for WebSocket connection management and reconnection logic
9. **Configuration management**: Use environment variables for all configurable values
10. **Documentation**: Keep code well-documented with docstrings and comments

## Testing Strategy

1. **Unit Tests**: Test individual functions and classes in isolation
2. **Integration Tests**: Test webhook flows, Devin API calls, database operations
3. **End-to-End Tests**: Test complete workflows from GitHub webhook to Telegram notification
4. **Load Testing**: Test webhook handling under high load
5. **Manual Testing**: Test Telegram bot commands and dashboard UX

## Deployment Checklist

1. Set up PostgreSQL database with proper backup strategy
2. Configure environment variables in production
3. Set up SSL certificates with Let's Encrypt
4. Configure Nginx reverse proxy
5. Set up process monitoring (systemd or Docker)
6. Configure log rotation and retention
7. Set up monitoring and alerting
8. Test webhook delivery from GitHub
9. Test Telegram bot functionality
10. Verify real-time dashboard updates

## Future Enhancements

1. **Slack Integration**: Add Slack as an alternative to Telegram
2. **Advanced Scheduling**: UI for creating complex scheduled tasks
3. **Custom Playbooks**: Allow users to select Devin playbooks for tasks
4. **Session Templates**: Pre-defined prompts for common tasks
5. **Cost Optimization**: Suggestions for reducing Devin costs
6. **Multi-User Support**: Extend beyond one-man developer use case
7. **Analytics Export**: Export metrics data for external analysis
8. **Webhook Replay**: Replay failed webhooks for debugging