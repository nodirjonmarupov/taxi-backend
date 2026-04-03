# 🚖 Taxi Backend System

Production-grade, scalable taxi platform backend built with Python, FastAPI, PostgreSQL, Redis, and Telegram Bot integration.

## ✨ Features

- ✅ **User & Driver Management** - Telegram-based registration
- ✅ **Smart Matching** - Distance-based driver assignment
- ✅ **Trip Lifecycle** - Complete order-to-payment flow
- ✅ **Real-time Updates** - Telegram bot notifications
- ✅ **Payment Processing** - Automated pricing & commissions
- ✅ **Rating System** - Driver ratings & reviews
- ✅ **Admin Dashboard** - Platform statistics & management
- ✅ **Clean Architecture** - Modular, testable, scalable

## 🏗️ Architecture

```
┌─────────────┐     ┌──────────────┐     ┌───────────────┐
│  Telegram   │────▶│   FastAPI    │────▶│  PostgreSQL   │
│     Bot     │     │   Backend    │     │   Database    │
└─────────────┘     └──────────────┘     └───────────────┘
                           │
                           │
                    ┌──────▼──────┐
                    │    Redis    │
                    │    Cache    │
                    └─────────────┘
```

## 🚀 Quick Start

### Using Docker (Recommended)

```bash
# Clone repository
git clone <repo>
cd taxi-backend

# Configure environment
cp .env.example .env
# Edit .env - set TELEGRAM_BOT_TOKEN

# Start services
docker-compose up -d

# API available at http://localhost:8000
# Docs at http://localhost:8000/docs
```

### Manual Setup

```bash
# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Setup database
createdb taxi_db

# Configure .env
cp .env.example .env

# Run application
python -m app.main
```

## 📋 Environment Configuration

```env
# Database
DATABASE_URL=postgresql+asyncpg://taxi_user:taxi_password@localhost:5432/taxi_db

# Redis
REDIS_URL=redis://localhost:6379/0

# Telegram Bot (Get from @BotFather)
TELEGRAM_BOT_TOKEN=your_token_here

# Business Logic
BASE_PRICE=50.0                 # Base fare
PRICE_PER_KM=15.0              # Per kilometer
COMMISSION_PERCENTAGE=20.0      # Platform fee
ORDER_TIMEOUT_SECONDS=300       # 5 minutes
SEARCH_RADIUS_KM=10.0          # Driver search radius
```

## 🔌 API Endpoints

### Users & Drivers

```
POST   /api/v1/users                          Create user
GET    /api/v1/users/{user_id}               Get user
GET    /api/v1/users/telegram/{telegram_id}  Get by Telegram ID
PATCH  /api/v1/users/{user_id}               Update user

POST   /api/v1/drivers                        Register driver
GET    /api/v1/drivers/{driver_id}           Get driver
PATCH  /api/v1/drivers/{driver_id}           Update driver
POST   /api/v1/drivers/{driver_id}/location  Update location
GET    /api/v1/drivers/{driver_id}/stats     Driver statistics
GET    /api/v1/drivers/{driver_id}/trips     Driver trip history
```

### Orders & Trips

```
POST   /api/v1/orders                         Create order
GET    /api/v1/orders/{order_id}             Get order
GET    /api/v1/orders/user/{user_id}         User order history
POST   /api/v1/orders/{order_id}/accept      Accept order
POST   /api/v1/orders/{order_id}/cancel      Cancel order

POST   /api/v1/trips/start                    Start trip
POST   /api/v1/trips/{trip_id}/complete      Complete trip
GET    /api/v1/trips/{trip_id}               Get trip details
GET    /api/v1/trips/estimate/price          Estimate price
POST   /api/v1/trips/ratings                 Rate driver
```

### Admin

```
GET    /api/v1/admin/stats                    Platform statistics
GET    /api/v1/admin/drivers                  List all drivers
GET    /api/v1/admin/orders/active           Active orders
```

## 🤖 Telegram Bot Usage

### For Users

1. Start bot: `/start`
2. Send location
3. Order taxi
4. Track driver
5. Complete trip
6. Rate driver

### For Drivers

1. Register as driver
2. Share car details
3. Go online
4. Accept orders
5. Start trip
6. Complete trip
7. View earnings

### Bot Commands

```
/start  - Start bot and register
/help   - Show help message

🚕 Order Taxi      - Request a ride
📍 Share Location  - Send pickup location
📜 My Orders       - View order history

🚗 Go Online      - Toggle driver status
📊 My Stats       - View earnings
📜 Trip History   - View completed trips
```

## 📊 Database Models

### Core Tables

- **users** - User profiles & authentication
- **drivers** - Driver details, car info, location
- **orders** - Taxi requests, status tracking
- **trips** - Active trips, distance, pricing
- **payments** - Payment records, commissions
- **ratings** - Driver ratings & reviews

### Relationships

```
User ──┬── Driver (1:1)
       └── Orders (1:N)

Driver ──── Trips (1:N)

Order ───── Trip (1:1)

Trip ──┬── Payment (1:1)
       └── Rating (1:1)
```

## 🔄 Order Flow

```
1. User sends location
   ↓
2. System creates order
   ↓
3. Match nearest driver (auto)
   ↓
4. Driver accepts
   ↓
5. Driver starts trip
   ↓
6. Trip in progress
   ↓
7. Driver completes trip
   ↓
8. Calculate price & commission
   ↓
9. Process payment
   ↓
10. User rates driver
```

## 📁 Project Structure

```
taxi-backend/
├── app/
│   ├── main.py                 # FastAPI app
│   ├── core/                   # Configuration
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── redis.py
│   │   └── logger.py
│   ├── models/                 # Database models
│   │   ├── user.py
│   │   └── order.py
│   ├── schemas/                # Pydantic schemas
│   │   ├── user.py
│   │   └── order.py
│   ├── crud/                   # Database operations
│   │   ├── user.py
│   │   └── order.py
│   ├── services/               # Business logic
│   │   ├── matching.py
│   │   └── trip.py
│   ├── api/v1/                 # API routes
│   │   └── routes.py
│   ├── bot/                    # Telegram bot
│   │   └── telegram_bot.py
│   └── utils/                  # Utilities
│       └── distance.py
├── logs/                       # Application logs
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── README.md
```

## 🔧 Key Technologies

- **FastAPI** - Modern async web framework
- **SQLAlchemy** - Async ORM
- **PostgreSQL** - Relational database
- **Redis** - Caching layer
- **Aiogram** - Telegram bot framework
- **Pydantic** - Data validation
- **Loguru** - Structured logging
- **Docker** - Containerization

## 📈 Performance Features

- ⚡ **Fully Async** - AsyncIO throughout
- 🚀 **Connection Pooling** - Database optimization
- 💾 **Redis Caching** - Hot data caching
- 🔄 **Background Tasks** - Order cleanup
- 📊 **Indexed Queries** - Fast database access

## 🔒 Security

- Environment-based secrets
- SQL injection protection
- Input validation
- Type safety
- CORS configuration

## 🧪 Testing

```bash
# Run tests
pytest

# With coverage
pytest --cov=app tests/

# Specific test
pytest tests/test_matching.py
```

## 📝 Logging

Logs in `logs/` directory:

- `app.log` - All logs (30 days)
- `error.log` - Errors only (60 days)
- Auto-rotation at 100MB
- Compression enabled

## 🐛 Troubleshooting

### Database Issues

```bash
# Check PostgreSQL
docker-compose ps postgres
docker-compose logs postgres

# Reset database
docker-compose down -v
docker-compose up -d
```

### Bot Not Responding

1. Verify `TELEGRAM_BOT_TOKEN` in `.env`
2. Check logs: `docker-compose logs app`
3. Restart: `docker-compose restart app`

### Port Already in Use

```bash
# Find process using port 8000
lsof -i :8000

# Change port in .env
PORT=8001
```

## 🚀 Deployment

### Production Checklist

- [ ] Set `DEBUG=False`
- [ ] Use strong `SECRET_KEY`
- [ ] Configure CORS properly
- [ ] Use production database
- [ ] Enable SSL/TLS
- [ ] Set up monitoring
- [ ] Configure backups
- [ ] Use reverse proxy (Nginx)

### Docker Production

```bash
# Build production image
docker build -t taxi-backend:prod .

# Run with production config
docker run -d \
  --name taxi-backend \
  -p 8000:8000 \
  --env-file .env.production \
  taxi-backend:prod
```

## 📊 Monitoring

### Health Checks

```bash
# API health
curl http://localhost:8000/health

# Database check
docker-compose exec postgres pg_isready

# Redis check
docker-compose exec redis redis-cli ping
```

### Logs

```bash
# Follow logs
docker-compose logs -f app

# Last 100 lines
docker-compose logs --tail=100 app

# Specific service
docker-compose logs postgres
```

## 🤝 Contributing

1. Fork repository
2. Create feature branch: `git checkout -b feature/amazing-feature`
3. Commit changes: `git commit -m 'Add amazing feature'`
4. Push to branch: `git push origin feature/amazing-feature`
5. Open Pull Request

## 📄 License

MIT License - see LICENSE file

## 🙏 Acknowledgments

- FastAPI team
- SQLAlchemy team
- Aiogram developers
- PostgreSQL community

---

**Built for scalability, designed for production** 🚀
