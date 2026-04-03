# 🚖 Taxi Backend System - Setup Instructions

## 📦 What's Included

This is a **complete, production-ready** taxi platform backend with:

✅ **FastAPI** REST API (async)
✅ **PostgreSQL** database with full schema
✅ **Redis** caching layer
✅ **Telegram Bot** for user/driver interaction
✅ **Docker** containerization
✅ **Clean Architecture** with modular design
✅ **Complete CRUD** operations
✅ **Driver Matching** algorithm
✅ **Trip Lifecycle** management
✅ **Payment** calculation & tracking
✅ **Rating** system
✅ **Admin** endpoints

## 🚀 Quick Start (3 Steps)

### Step 1: Get Telegram Bot Token

1. Open Telegram and message [@BotFather](https://t.me/BotFather)
2. Send `/newbot`
3. Choose a name: e.g., "My Taxi Bot"
4. Choose a username: e.g., "mytaxitest_bot"
5. Copy the token (looks like: `123456:ABC-DEF...`)

### Step 2: Configure

```bash
# Navigate to project
cd taxi-backend

# Create environment file
cp .env.example .env

# Edit .env and set your token
nano .env
# Change: TELEGRAM_BOT_TOKEN=your_token_here
```

### Step 3: Start

```bash
# Start all services with Docker
./start.sh

# OR manually:
docker-compose up -d

# Wait ~10 seconds for startup
```

## ✅ Verify Installation

```bash
# 1. Check services are running
docker-compose ps
# Should show: postgres, redis, app - all "Up"

# 2. Test API health
curl http://localhost:8000/health
# Should return: {"status":"healthy"}

# 3. Open API documentation
open http://localhost:8000/docs
# (or visit in browser)

# 4. Test Telegram bot
# Find your bot in Telegram and send /start
```

## 📱 Using the Telegram Bot

### As a User

1. Find your bot in Telegram
2. Send `/start`
3. Click "📍 Share Location"
4. Share your location
5. Click "🚕 Order Taxi"
6. Bot will find nearest driver
7. Track your ride

### As a Driver

1. Send `/start` to bot
2. Click "Register as Driver"
3. Share your phone number
4. Enter car details:
   - Car number/plate
   - Car model
   - Car color
5. Click "🚗 Go Online"
6. Share your location
7. Receive and accept orders
8. Start trips
9. Complete trips
10. View earnings with "📊 My Stats"

## 🔧 Configuration

### Environment Variables (.env)

```env
# Required - Get from @BotFather
TELEGRAM_BOT_TOKEN=your_bot_token_here

# Database (default works with Docker)
DATABASE_URL=postgresql+asyncpg://taxi_user:taxi_password@localhost:5432/taxi_db

# Redis (default works with Docker)
REDIS_URL=redis://localhost:6379/0

# Business Logic (customize as needed)
BASE_PRICE=50.0                 # Base fare in your currency
PRICE_PER_KM=15.0              # Price per kilometer
COMMISSION_PERCENTAGE=20.0      # Platform commission (%)
ORDER_TIMEOUT_SECONDS=300       # Order expiration (5 min)
SEARCH_RADIUS_KM=10.0          # Driver search radius

# Server
DEBUG=True                      # Set False for production
PORT=8000
```

## 🧪 Testing the API

### Option 1: Use Test Script

```bash
# Install requests library
pip install requests

# Run automated test
python test_api.py

# This will:
# 1. Create a user
# 2. Register a driver
# 3. Create an order
# 4. Match driver to order
# 5. Start trip
# 6. Complete trip
# 7. Process payment
# 8. Rate driver
```

### Option 2: Manual API Testing

```bash
# 1. Create a user
curl -X POST http://localhost:8000/api/v1/users \
  -H "Content-Type: application/json" \
  -d '{
    "telegram_id": 123456789,
    "first_name": "John",
    "phone": "+1234567890",
    "role": "user"
  }'

# 2. Create an order
curl -X POST "http://localhost:8000/api/v1/orders?user_id=1" \
  -H "Content-Type: application/json" \
  -d '{
    "pickup_latitude": 37.7749,
    "pickup_longitude": -122.4194,
    "destination_latitude": 37.7849,
    "destination_longitude": -122.4094
  }'

# 3. Get admin statistics
curl http://localhost:8000/api/v1/admin/stats | jq
```

### Option 3: Swagger UI

Visit http://localhost:8000/docs for interactive API testing

## 📁 Project Structure

```
taxi-backend/
├── app/
│   ├── main.py              # FastAPI application
│   ├── api/v1/routes.py     # All API endpoints
│   ├── models/              # Database models
│   │   ├── user.py          # User, Driver, Rating
│   │   └── order.py         # Order, Trip, Payment
│   ├── schemas/             # Pydantic validation
│   │   ├── user.py
│   │   └── order.py
│   ├── crud/                # Database operations
│   │   ├── user.py
│   │   └── order.py
│   ├── services/            # Business logic
│   │   ├── matching.py      # Driver matching
│   │   └── trip.py          # Trip lifecycle
│   ├── bot/                 # Telegram bot
│   │   └── telegram_bot.py
│   ├── core/                # Configuration
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── redis.py
│   │   └── logger.py
│   └── utils/               # Utilities
│       └── distance.py      # Haversine distance
├── logs/                    # Application logs
├── docker-compose.yml       # Docker services
├── Dockerfile              # App container
├── requirements.txt        # Python dependencies
├── test_api.py            # API test script
├── start.sh               # Quick start script
└── README.md              # Full documentation
```

## 🐳 Docker Commands

```bash
# Start services
docker-compose up -d

# View logs
docker-compose logs -f app

# Stop services
docker-compose stop

# Restart
docker-compose restart

# Stop and remove (keeps data)
docker-compose down

# Stop and remove all (deletes data!)
docker-compose down -v

# Rebuild after code changes
docker-compose up -d --build
```

## 🗄️ Database Access

```bash
# Access PostgreSQL
docker-compose exec postgres psql -U taxi_user -d taxi_db

# Some useful queries:
SELECT COUNT(*) FROM users;
SELECT COUNT(*) FROM drivers WHERE is_available = true;
SELECT * FROM orders WHERE status = 'pending';
SELECT * FROM trips ORDER BY created_at DESC LIMIT 10;
```

## 📊 Monitoring

```bash
# Check service health
curl http://localhost:8000/health

# View platform statistics
curl http://localhost:8000/api/v1/admin/stats | jq

# Check active orders
curl http://localhost:8000/api/v1/admin/orders/active | jq

# View logs
tail -f logs/app.log
tail -f logs/error.log
```

## 🐛 Troubleshooting

### Services won't start

```bash
# Check if ports are in use
lsof -i :8000   # API
lsof -i :5432   # PostgreSQL
lsof -i :6379   # Redis

# View error logs
docker-compose logs app
docker-compose logs postgres
docker-compose logs redis
```

### Telegram bot not responding

1. Verify token in `.env` is correct
2. Check bot is started: `docker-compose logs app | grep "Starting Telegram bot"`
3. Restart app: `docker-compose restart app`
4. Make sure bot isn't blocked by @BotFather

### Database connection failed

```bash
# Check PostgreSQL is running
docker-compose ps postgres

# Restart database
docker-compose restart postgres

# Check database exists
docker-compose exec postgres psql -U taxi_user -l
```

### Port 8000 already in use

```bash
# Option 1: Find and kill process
lsof -i :8000
kill -9 <PID>

# Option 2: Change port in .env
PORT=8001
docker-compose down
docker-compose up -d
```

## 🔒 Security Notes

### For Development

- Default `.env` settings are fine
- Debug mode is enabled
- CORS allows all origins

### For Production

1. Set `DEBUG=False`
2. Generate strong `SECRET_KEY`:
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```
3. Configure CORS properly in `app/main.py`
4. Use production database credentials
5. Enable SSL/TLS
6. Set up firewall rules
7. Regular security updates

## 📈 Scaling

### Horizontal Scaling

```yaml
# In docker-compose.yml
app:
  deploy:
    replicas: 3  # Run 3 instances
```

### Database Optimization

```sql
-- Add indexes for performance
CREATE INDEX idx_orders_status ON orders(status);
CREATE INDEX idx_drivers_location ON drivers(current_latitude, current_longitude);
```

### Redis Caching

- Configured and ready
- Customize TTL in `app/core/redis.py`

## 📚 Additional Documentation

- **README.md** - Full project documentation
- **API Docs** - http://localhost:8000/docs
- **ReDoc** - http://localhost:8000/redoc

## 🤝 Support

### Getting Help

1. Check logs: `docker-compose logs -f`
2. Review documentation
3. Test with `test_api.py`
4. Check Telegram bot with `/help`

### Common Questions

**Q: How do I change pricing?**
A: Edit `BASE_PRICE` and `PRICE_PER_KM` in `.env`

**Q: How do I add more drivers?**
A: Use Telegram bot "Register as Driver" or POST to `/api/v1/drivers`

**Q: Where is data stored?**
A: PostgreSQL in Docker volume `taxi_postgres_data`

**Q: How do I backup data?**
A: `docker-compose exec postgres pg_dump -U taxi_user taxi_db > backup.sql`

**Q: Can I run without Docker?**
A: Yes! Install PostgreSQL, Redis, Python deps, then `python -m app.main`

## ✨ Features Checklist

- [x] User registration via Telegram
- [x] Driver registration with car details
- [x] Location sharing and tracking
- [x] Order creation and matching
- [x] Distance-based driver search
- [x] Automatic price calculation
- [x] Trip lifecycle management
- [x] Payment processing
- [x] Rating system
- [x] Driver statistics
- [x] Admin dashboard
- [x] Real-time notifications
- [x] Background tasks
- [x] Comprehensive logging
- [x] Docker support
- [x] API documentation
- [x] Clean architecture

## 🎉 You're All Set!

Your taxi backend is ready for:
- ✅ Development and testing
- ✅ Demo and presentation
- ✅ Production deployment (with proper security)
- ✅ Scaling to 1000+ drivers

Happy coding! 🚀
