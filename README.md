# DevinBot - Custom Devin API Integration Platform

A custom backend application that integrates with Devin's API to automate software development workflows for a one-man developer. Features GitHub webhook integration, Telegram-based control and monitoring, scheduled task execution, and real-time observability through a mobile web dashboard.

## Features

- **GitHub Webhook Integration**: Automatically trigger Devin sessions for PR reviews and issue resolution
- **Telegram Bot**: Two-way Telegram integration for monitoring job status and controlling Devin sessions
- **Scheduled Tasks**: Create and manage scheduled tasks that run Devin sessions with custom prompts
- **Real-time Observability**: Mobile web dashboard showing success rates, session counts, cost consumption, and active/completed sessions
- **Multi-Repository Support**: Manage multiple GitHub repositories with Telegram topic mapping
- **WebSocket Updates**: Real-time metrics and session status updates

## Architecture

```
GitHub Webhooks → FastAPI Backend → Devin API
                                        ↓
Telegram Bot ← FastAPI Backend ← Devin Sessions/Sessions/Metrics
                                        ↓
                                  Next.js Mobile Dashboard
```

## Tech Stack

### Backend
- **Framework**: FastAPI (Python 3.11+)
- **Database**: PostgreSQL with SQLAlchemy ORM
- **Task Scheduling**: APScheduler
- **HTTP Client**: httpx for async Devin API calls
- **Telegram**: python-telegram-bot library
- **WebSockets**: FastAPI WebSocket support

### Frontend
- **Framework**: Next.js 14+ with App Router
- **Styling**: Tailwind CSS for mobile-first design
- **Real-time**: WebSocket client for live updates
- **State Management**: React hooks

## Setup Instructions

### Prerequisites

- Python 3.11+
- Node.js 18+
- PostgreSQL 12+
- Devin API credentials
- GitHub personal access token
- Telegram bot token

### Backend Setup

1. **Navigate to backend directory**
```bash
cd backend
```

2. **Create virtual environment**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Configure environment variables**
```bash
cp .env.example .env
```

Edit `.env` with your actual values:
```env
# Devin API Configuration
DEVIN_API_KEY=your_devin_api_key_here
DEVIN_ORG_ID=your_devin_org_id_here

# GitHub Configuration
GITHUB_WEBHOOK_SECRET=your_github_webhook_secret_here
GITHUB_TOKEN=your_github_personal_access_token_here

# Telegram Configuration
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
TELEGRAM_CHAT_ID=your_telegram_main_chat_id_here

# Database Configuration
DATABASE_URL=postgresql://user:password@localhost/devinbot

# Application Configuration
APP_BASE_URL=http://localhost:8000
LOG_LEVEL=INFO

# CORS Configuration
CORS_ORIGINS=http://localhost:3000,http://localhost:8000
```

5. **Initialize database**
```bash
# Create database
createdb devinbot

# Run migrations
alembic upgrade head
```

6. **Start the backend server**
```bash
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend Setup

1. **Navigate to frontend directory**
```bash
cd frontend
```

2. **Install dependencies**
```bash
npm install
```

3. **Configure environment variables**
Create a `.env.local` file:
```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

4. **Start the development server**
```bash
npm run dev
```

5. **Open the dashboard**
Navigate to `http://localhost:3000`

## Getting API Credentials

### Devin API

1. Go to [app.devin.ai](https://app.devin.ai)
2. Navigate to Settings > Service Users
3. Create a service user with the following permissions:
   - `UseDevinSessions` - Create and manage sessions
   - `ImpersonateOrgSessions` - Create sessions on behalf of users
   - `UseReviewManual` - Trigger PR reviews
   - `ViewOrgMetrics` - Access usage metrics
   - `UseLocalAnalyticsAPI` - Access Analytics API v2
4. Copy the API token (shown only once)
5. Get your organization ID from the Devin UI or API

### GitHub

1. Go to GitHub Settings > Developer settings > Personal access tokens
2. Generate a new token with `repo` scope
3. Generate webhook secrets (use: `openssl rand -hex 32`)
   - Generate one default secret for the `.env` file
   - Generate unique secrets for each repository you want to add (recommended for better security)

### Telegram

1. Create a bot via [@BotFather](https://t.me/botfather) on Telegram
2. Copy the bot token
3. Get your chat ID by messaging [@userinfobot](https://t.me/userinfobot)

## GitHub Webhook Setup

1. Go to your GitHub repository Settings > Webhooks
2. Add a new webhook with:
   - **Payload URL**: `http://your-domain.com/webhooks/github`
   - **Content type**: `application/json`
   - **Secret**: Use a unique secret for this repository (recommended) or your default secret
   - **Events**: Select "Pull requests" and "Issues"
3. When adding the repository via the API, specify the webhook secret you used
4. The system will verify webhooks using the repository-specific secret if provided, falling back to the default secret

## API Endpoints

### Webhooks
- `POST /webhooks/github` - GitHub webhook receiver

### Sessions
- `GET /api/sessions/` - List sessions
- `POST /api/sessions/` - Create new session
- `GET /api/sessions/{id}` - Get session details
- `POST /api/sessions/{id}/cancel` - Cancel session

### Metrics
- `GET /api/metrics/` - Get observability metrics
- `GET /api/metrics/repositories` - Get repository metrics
- `GET /api/metrics/realtime` - Get real-time metrics

### Scheduled Tasks
- `GET /api/scheduled-tasks/` - List scheduled tasks
- `POST /api/scheduled-tasks/` - Create scheduled task
- `GET /api/scheduled-tasks/{id}` - Get task details
- `PUT /api/scheduled-tasks/{id}` - Update task
- `DELETE /api/scheduled-tasks/{id}` - Delete task

### Repositories
- `GET /api/repositories/` - List repositories
- `POST /api/repositories/` - Create repository
- `GET /api/repositories/{id}` - Get repository details
- `PUT /api/repositories/{id}` - Update repository
- `DELETE /api/repositories/{id}` - Delete repository

### WebSocket
- `WS /ws/ws` - Real-time metrics updates

## Telegram Commands

- `/status` - Show active sessions for current repo topic
- `/cancel <session_id>` - Cancel a running session
- `/create <prompt>` - Create new session with custom prompt
- `/metrics` - Show current metrics for repository
- `/help` - List available commands

## Database Schema

### Repositories
- `id` - UUID primary key
- `github_repo_path` - GitHub repository path (e.g., "owner/repo")
- `telegram_chat_id` - Telegram chat ID for notifications
- `telegram_topic_id` - Optional Telegram topic ID
- `devin_org_id` - Devin organization ID
- `webhook_secret` - GitHub webhook secret
- `enabled` - Boolean flag

### Sessions
- `id` - UUID primary key
- `devin_session_id` - Devin session ID
- `repository_id` - Foreign key to repositories
- `trigger_type` - pr_review, issue, scheduled, manual
- `trigger_context` - JSON context data
- `status` - pending, running, completed, failed, cancelled
- `prompt` - Session prompt
- `devin_mode` - normal, fast, lite, ultra, fusion
- `error_message` - Error message if failed
- `created_at`, `updated_at`, `completed_at` - Timestamps

### Scheduled Tasks
- `id` - UUID primary key
- `repository_id` - Foreign key to repositories
- `name` - Task name
- `cron_expression` - APScheduler cron expression
- `prompt` - Task prompt
- `devin_mode` - Devin agent mode
- `enabled` - Boolean flag
- `last_run_at`, `next_run_at` - Timestamps

## Development

### Running Tests
```bash
cd backend
pytest tests/
```

### Database Migrations
```bash
# Create new migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback migration
alembic downgrade -1
```

### Project Structure
```
devinbot/
├── backend/
│   ├── app/
│   │   ├── api/          # API endpoints
│   │   ├── core/         # Configuration
│   │   ├── db/           # Database session
│   │   ├── models/       # Database models
│   │   └── services/     # Business logic
│   ├── alembic/          # Database migrations
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── app/          # Next.js app directory
│   │   ├── components/   # React components
│   │   └── hooks/        # Custom hooks
│   └── package.json
└── AGENTS.md             # Project documentation
```

## Troubleshooting

### Backend Issues

**Database connection error**
- Ensure PostgreSQL is running
- Check DATABASE_URL in .env
- Verify database exists: `psql -l`

**Devin API authentication error**
- Verify DEVIN_API_KEY and DEVIN_ORG_ID
- Check service user permissions
- Ensure API key is valid (not expired)

**Telegram bot not responding**
- Verify TELEGRAM_BOT_TOKEN
- Check bot is started via BotFather
- Ensure chat ID is correct

### Frontend Issues

**API connection error**
- Check NEXT_PUBLIC_API_URL in .env.local
- Ensure backend is running on correct port
- Verify CORS settings in backend

**WebSocket connection error**
- Check backend WebSocket endpoint is accessible
- Verify ws:// URL format (not http://)
- Check firewall/network settings

## Deployment

### Backend Deployment

1. **Set up production database**
2. **Configure production environment variables**
3. **Run migrations**: `alembic upgrade head`
4. **Install gunicorn**: `pip install gunicorn`
5. **Run with gunicorn**: `gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker`
6. **Set up reverse proxy (nginx)**
7. **Configure SSL with Let's Encrypt**

### Frontend Deployment

1. **Build production bundle**: `npm run build`
2. **Deploy to Vercel/Netlify or serve with nginx**
3. **Update NEXT_PUBLIC_API_URL to production backend URL**

## Security Considerations

- Never commit `.env` files to version control
- Use strong webhook secrets
- Implement rate limiting for public endpoints
- Keep dependencies updated
- Use HTTPS in production
- Rotate API keys regularly

## License

This project is for personal use. Please respect Devin's API terms of service.

## Support

For issues related to:
- **Devin API**: Check [Devin documentation](https://docs.devin.ai/api-reference/overview)
- **GitHub Webhooks**: Check [GitHub documentation](https://docs.github.com/en/developers/webhooks-and-events/webhooks)
- **Telegram Bot API**: Check [Telegram documentation](https://core.telegram.org/bots/api)