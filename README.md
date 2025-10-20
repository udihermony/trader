# 🚀 AlgoTrader - Comprehensive Algorithmic Trading Platform

A production-ready algorithmic trading platform built with **Python FastAPI** and deployed on **AWS**. This platform connects to the Indian stock market via the **Fyers Trading API**, processes external alerts (e.g., from **Chartlink**), and automatically executes trades according to predefined trading strategies.

## 🎯 Features

### Core Functionality
- **Strategy Management**: Create, edit, and manage trading strategies with customizable parameters
- **Alert Processing**: Real-time trading signals from Chartlink via webhook integration
- **Order Execution**: Live market trades through Fyers API v3 with multiple order types
- **Portfolio Management**: Real-time position tracking, P&L monitoring, and performance analytics
- **Risk Management**: Built-in position sizing, exposure limits, and safety safeguards
- **Multi-User Support**: JWT-based authentication with role-based permissions

### Technical Features
- **Async Architecture**: High-performance async/await throughout
- **Real-time Processing**: Redis-based task queuing for signal processing
- **Database**: PostgreSQL with SQLAlchemy ORM and Alembic migrations
- **Caching**: Redis for session management and data caching
- **Monitoring**: Comprehensive logging with Loguru and health checks
- **Security**: JWT authentication, webhook signature verification, rate limiting

## 🏗️ Architecture

```
Signal Source (Chartlink)
   ↓
[ FastAPI Webhook Endpoint ]
   ↓ validates and enqueues signals
[ Redis Queue ]
   ↓
[ Async Worker (Trade Engine) ]
   ↓ applies strategy logic
[ Fyers Trading API ]
   ↓ executes and confirms trades
[ PostgreSQL DB ]
   ↳ logs trades, positions, users, strategies
[ React Dashboard (optional) ]
   ↳ visualizes strategies, trades, and performance
```

## 🛠️ Tech Stack

### Backend
- **Language**: Python 3.10+
- **Framework**: FastAPI (async API server)
- **Database**: PostgreSQL with SQLAlchemy + Alembic
- **Cache/Queue**: Redis
- **Trading API**: Fyers API v3
- **Authentication**: JWT + OAuth2 (Fyers)
- **HTTP Client**: httpx (async)
- **Logging**: Loguru + CloudWatch
- **Configuration**: Pydantic Settings

### Infrastructure
- **Hosting**: AWS EC2 (Mumbai region for low latency)
- **Database**: AWS RDS (PostgreSQL)
- **Caching**: AWS ElastiCache (Redis)
- **Secrets**: AWS Systems Manager (SSM)
- **Reverse Proxy**: Nginx with Let's Encrypt (HTTPS)
- **Monitoring**: CloudWatch + Grafana + Loki
- **CI/CD**: GitHub Actions → EC2 deploy

## 📦 Installation

### Prerequisites
- Python 3.10+
- Docker & Docker Compose
- PostgreSQL 15+
- Redis 7+
- Fyers API credentials
- Chartlink webhook access

### Local Development

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/alogtrader.git
   cd alogtrader
   ```

2. **Set up virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment**
   ```bash
   cp env.example .env
   # Edit .env with your actual configuration
   ```

5. **Start services with Docker Compose**
   ```bash
   docker-compose up -d
   ```

6. **Run database migrations**
   ```bash
   alembic upgrade head
   ```

7. **Start the application**
   ```bash
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

### Production Deployment

1. **Deploy to AWS EC2**
   ```bash
   # Run the deployment script
   sudo bash scripts/deploy.sh
   ```

2. **Configure SSL certificates**
   ```bash
   certbot --nginx -d yourdomain.com
   ```

3. **Set up monitoring**
   ```bash
   # Monitor logs
   journalctl -u alogtrader -f
   
   # Check health
   curl http://yourdomain.com/api/v1/health/
   ```

## 🔧 Configuration

### Environment Variables

Key configuration options in `.env`:

```env
# Application
APP_NAME="AlgoTrader"
DEBUG=false
ENVIRONMENT=production

# Database
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/alogtrader

# Redis
REDIS_URL=redis://localhost:6379/0

# Fyers API
FYERS_APP_ID=your_fyers_app_id
FYERS_SECRET_KEY=your_fyers_secret_key
FYERS_REDIRECT_URI=http://yourdomain.com/auth/fyers/callback

# JWT
JWT_SECRET_KEY=your-super-secret-jwt-key

# Chartlink Webhook
CHARTLINK_WEBHOOK_SECRET=your_chartlink_webhook_secret

# Risk Management
MAX_POSITION_SIZE=100000
MAX_DAILY_LOSS=5000
MAX_DAILY_TRADES=50
```

### AWS SSM Integration

For production, store sensitive values in AWS Systems Manager Parameter Store:

```bash
# Store secrets in SSM
aws ssm put-parameter --name "/alogtrader/jwt_secret_key" --value "your-secret" --type "SecureString"
aws ssm put-parameter --name "/alogtrader/fyers_secret_key" --value "your-secret" --type "SecureString"
```

## 📚 API Documentation

### Authentication

1. **Register a new user**
   ```bash
   curl -X POST "http://localhost:8000/api/v1/auth/register" \
        -H "Content-Type: application/json" \
        -d '{"email": "user@example.com", "username": "trader", "password": "password123"}'
   ```

2. **Login and get JWT token**
   ```bash
   curl -X POST "http://localhost:8000/api/v1/auth/login" \
        -H "Content-Type: application/json" \
        -d '{"email": "user@example.com", "password": "password123"}'
   ```

3. **Authenticate with Fyers**
   ```bash
   curl -X POST "http://localhost:8000/api/v1/auth/fyers/auth" \
        -H "Authorization: Bearer YOUR_JWT_TOKEN" \
        -H "Content-Type: application/json" \
        -d '{"auth_code": "your_fyers_auth_code"}'
   ```

### Strategy Management

1. **Create a strategy**
   ```bash
   curl -X POST "http://localhost:8000/api/v1/strategies/" \
        -H "Authorization: Bearer YOUR_JWT_TOKEN" \
        -H "Content-Type: application/json" \
        -d '{
          "name": "Momentum Strategy",
          "strategy_type": "momentum",
          "parameters": {"lookback_period": 20},
          "position_sizing_rules": {"percentage_of_capital": 5}
        }'
   ```

2. **Get all strategies**
   ```bash
   curl -X GET "http://localhost:8000/api/v1/strategies/" \
        -H "Authorization: Bearer YOUR_JWT_TOKEN"
   ```

### Trading Operations

1. **Place an order**
   ```bash
   curl -X POST "http://localhost:8000/api/v1/fyers/orders" \
        -H "Authorization: Bearer YOUR_JWT_TOKEN" \
        -H "Content-Type: application/json" \
        -d '{
          "symbol": "NSE:RELIANCE",
          "side": "BUY",
          "quantity": 10,
          "order_type": "market"
        }'
   ```

2. **Get portfolio**
   ```bash
   curl -X GET "http://localhost:8000/api/v1/portfolio/" \
        -H "Authorization: Bearer YOUR_JWT_TOKEN"
   ```

### Webhook Integration

**Chartlink webhook endpoint**:
```bash
curl -X POST "http://localhost:8000/api/v1/webhooks/chartlink" \
     -H "Content-Type: application/json" \
     -H "X-Chartlink-Signature: your_signature" \
     -d '{
       "symbol": "NSE:RELIANCE",
       "action": "BUY",
       "price": 2500.50,
       "quantity": 10,
       "message": "Strong momentum signal"
     }'
```

## 🧪 Testing

### Run Tests
```bash
# Install test dependencies
pip install pytest pytest-asyncio pytest-cov

# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html

# Run specific test file
pytest tests/test_trade_engine.py -v
```

### Test Webhook
```bash
# Send test signal
curl -X POST "http://localhost:8000/api/v1/webhooks/test-signal" \
     -H "Content-Type: application/json" \
     -d '{
       "symbol": "NSE:RELIANCE",
       "action": "BUY",
       "price": 2500.50,
       "quantity": 10,
       "message": "Test signal"
     }'
```

## 📊 Monitoring

### Health Checks
- **Basic**: `GET /api/v1/health/`
- **Detailed**: `GET /api/v1/health/detailed`
- **Metrics**: `GET /api/v1/health/metrics`

### Logs
```bash
# Application logs
docker-compose logs -f app

# Nginx logs
tail -f /var/log/nginx/access.log
tail -f /var/log/nginx/error.log

# System logs
journalctl -u alogtrader -f
```

### Metrics
- Queue sizes (Redis)
- Database connections
- API response times
- Trade execution metrics
- Error rates

## 🔒 Security

### Authentication
- JWT tokens with configurable expiration
- Refresh token mechanism
- Password hashing with bcrypt

### API Security
- Rate limiting on endpoints
- Webhook signature verification
- CORS configuration
- HTTPS enforcement in production

### Data Protection
- Encrypted storage of Fyers credentials
- AWS SSM for sensitive configuration
- Database connection encryption

## 🚀 Deployment

### AWS EC2 Deployment

1. **Launch EC2 instance** (Ubuntu 22.04 LTS, t3.medium or larger)
2. **Configure security groups** (ports 22, 80, 443)
3. **Run deployment script**:
   ```bash
   sudo bash scripts/deploy.sh
   ```
4. **Configure domain** and SSL certificates
5. **Set up monitoring** and alerting

### Docker Deployment

```bash
# Development
docker-compose up -d

# Production
docker-compose -f docker-compose.prod.yml up -d
```

### CI/CD Pipeline

GitHub Actions workflow for automated deployment:

```yaml
name: Deploy to AWS
on:
  push:
    branches: [main]
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Deploy to EC2
        run: |
          # SSH to EC2 and pull latest code
          # Restart services
```

## 📈 Performance

### Optimization Features
- Async/await throughout the application
- Connection pooling for database and Redis
- Efficient Redis data structures for queuing
- Nginx reverse proxy with caching
- Gzip compression

### Scaling Considerations
- Horizontal scaling with multiple app instances
- Redis Cluster for high availability
- Database read replicas
- CDN for static assets

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## ⚠️ Disclaimer

This software is for educational and research purposes only. Trading involves substantial risk of loss and is not suitable for all investors. Past performance is not indicative of future results. Always consult with a qualified financial advisor before making investment decisions.

## 📞 Support

- **Documentation**: [API Docs](http://localhost:8000/docs)
- **Issues**: [GitHub Issues](https://github.com/yourusername/alogtrader/issues)
- **Discussions**: [GitHub Discussions](https://github.com/yourusername/alogtrader/discussions)

## 🙏 Acknowledgments

- [Fyers API](https://fyers.in/) for trading API
- [Chartlink](https://chartlink.com/) for signal integration
- [FastAPI](https://fastapi.tiangolo.com/) for the web framework
- [SQLAlchemy](https://www.sqlalchemy.org/) for ORM
- [Redis](https://redis.io/) for caching and queuing

---

**Happy Trading! 📈**
