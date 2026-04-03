# 🚀 QUICK START GUIDE

## Prerequisites
- Docker & Docker Compose installed
- Telegram Bot Token (from @BotFather on Telegram)

## Step 1: Setup
```bash
# Copy environment template
cp .env.example .env

# Edit .env and add your bot token
nano .env  # or use your preferred editor

# Required: Set TELEGRAM_BOT_TOKEN
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
```

## Step 2: Start Services
```bash
# Option A: Using script
./start.sh

# Option B: Using docker-compose
docker-compose up -d

# Option C: Using Makefile
make up
```

## Step 3: Verify
```bash
# Check if services are running
docker-compose ps

# View logs
docker-compose logs -f app

# Access API docs
# Open browser: http://localhost:8000/docs
```

## Step 4: Test Telegram Bot
1. Open Telegram
2. Find your bot (search by username)
3. Send `/start`
4. Try commands:
   - `/register_user` - Register as passenger
   - `/register_driver` - Register as driver

## Common Commands

### Service Management
```bash
# Start services
docker-compose up -d

# Stop services
docker-compose down

# View logs
docker-compose logs -f app

# Restart services
docker-compose restart
```

### Database
```bash
# Access database shell
docker-compose exec db psql -U postgres -d taxi_db

# Run migrations
docker-compose exec app alembic upgrade head

# Create new migration
docker-compose exec app alembic revision --autogenerate -m "description"
```

### Development
```bash
# Access app container
docker-compose exec app /bin/bash

# Run tests
docker-compose exec app pytest

# View application logs
tail -f logs/app.log
```

## API Examples

### Create User
```bash
curl -X POST "http://localhost:8000/api/v1/users/" \
  -H "Content-Type: application/json" \
  -d '{
    "telegram_id": "123456789",
    "username": "john_doe",
    "first_name": "John",
    "role": "user"
  }'
```

### Create Order
```bash
curl -X POST "http://localhost:8000/api/v1/orders/" \
  -H "Content-Type: application/json" \
  -d '{
    "pickup_latitude": 40.7128,
    "pickup_longitude": -74.0060,
    "passenger_count": 1
  }?user_id=1'
```

### Get Statistics
```bash
curl "http://localhost:8000/api/v1/admin/stats"
```

## Troubleshooting

### Bot not responding
- Check logs: `docker-compose logs app`
- Verify TELEGRAM_BOT_TOKEN in .env
- Test token: Send message to bot on Telegram

### Database connection error
- Ensure PostgreSQL is running: `docker-compose ps`
- Check DATABASE_URL in .env
- Restart: `docker-compose restart db`

### Port already in use
- Change port in docker-compose.yml
- Or stop conflicting service on port 8000

## Environment Variables

Required:
- `TELEGRAM_BOT_TOKEN` - Your Telegram bot token

Optional (with defaults):
- `DATABASE_URL` - Database connection string
- `REDIS_URL` - Redis connection string
- `SECRET_KEY` - Application secret (auto-generated if not set)
- `DEFAULT_COMMISSION_RATE` - Platform commission (default: 0.15)
- `BASE_PRICE` - Base fare (default: 2.0)
- `BASE_PRICE_PER_KM` - Price per km (default: 1.5)
- `DRIVER_SEARCH_RADIUS_KM` - Search radius (default: 10)

## URLs

- API: http://localhost:8000
- Interactive API Docs: http://localhost:8000/docs
- Alternative Docs: http://localhost:8000/redoc
- Health Check: http://localhost:8000/health

## Next Steps

1. Test user flow:
   - Register user via Telegram
   - Create order
   - View order history

2. Test driver flow:
   - Register driver
   - Go online (/available)
   - Update location
   - Accept orders

3. Monitor system:
   - Check admin stats
   - View logs
   - Monitor active orders

## Support

For detailed documentation, see README.md

Common issues and solutions:
- Docker not running → Start Docker Desktop
- Port conflicts → Change ports in docker-compose.yml
- Database errors → Reset: `docker-compose down -v && docker-compose up -d`
