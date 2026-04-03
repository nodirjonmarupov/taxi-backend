# 🚀 Production Deployment Guide

## Cloud Deployment Options

### Option 1: AWS Deployment

#### Architecture
```
Internet → ALB → ECS (FastAPI) → RDS PostgreSQL
                                → ElastiCache Redis
```

#### Steps

1. **Create RDS PostgreSQL Instance**
```bash
aws rds create-db-instance \
  --db-instance-identifier taxi-db \
  --db-instance-class db.t3.medium \
  --engine postgres \
  --master-username taxiuser \
  --master-user-password <password> \
  --allocated-storage 20
```

2. **Create ElastiCache Redis**
```bash
aws elasticache create-cache-cluster \
  --cache-cluster-id taxi-redis \
  --cache-node-type cache.t3.micro \
  --engine redis \
  --num-cache-nodes 1
```

3. **Deploy with ECS**
```bash
# Build and push Docker image
docker build -t taxi-backend .
docker tag taxi-backend:latest <account-id>.dkr.ecr.<region>.amazonaws.com/taxi-backend:latest
docker push <account-id>.dkr.ecr.<region>.amazonaws.com/taxi-backend:latest

# Create ECS service
aws ecs create-service \
  --cluster taxi-cluster \
  --service-name taxi-backend \
  --task-definition taxi-backend:1 \
  --desired-count 2 \
  --load-balancers targetGroupArn=<arn>,containerName=backend,containerPort=8000
```

### Option 2: DigitalOcean App Platform

1. **Connect GitHub Repository**
2. **Configure Environment Variables**
3. **Add Database Component** (Managed PostgreSQL)
4. **Add Redis Component** (Managed Redis)
5. **Deploy**

Environment Variables:
```bash
DATABASE_URL=${db.DATABASE_URL}
REDIS_URL=${redis.REDIS_URL}
TELEGRAM_BOT_TOKEN=<your-token>
```

### Option 3: Google Cloud Platform

#### Using Cloud Run + Cloud SQL

```bash
# Build and deploy
gcloud builds submit --tag gcr.io/<project-id>/taxi-backend
gcloud run deploy taxi-backend \
  --image gcr.io/<project-id>/taxi-backend \
  --platform managed \
  --add-cloudsql-instances <project-id>:<region>:taxi-db \
  --set-env-vars DATABASE_URL=<cloud-sql-url> \
  --allow-unauthenticated
```

## Load Balancer Configuration

### Nginx Configuration

```nginx
upstream backend {
    least_conn;
    server backend1:8000;
    server backend2:8000;
    server backend3:8000;
}

server {
    listen 80;
    server_name api.taxibackend.com;

    location / {
        proxy_pass http://backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /health {
        access_log off;
        proxy_pass http://backend/health;
    }
}
```

## SSL/TLS Setup

### Using Let's Encrypt

```bash
# Install certbot
sudo apt-get update
sudo apt-get install certbot python3-certbot-nginx

# Get certificate
sudo certbot --nginx -d api.taxibackend.com

# Auto-renewal
sudo certbot renew --dry-run
```

## Environment-Specific Configuration

### Production Environment Variables

```bash
# Application
APP_NAME=TaxiBackend
ENVIRONMENT=production
DEBUG=False

# Database (use connection pooling)
DATABASE_URL=postgresql+asyncpg://user:pass@prod-db:5432/taxi_db
DATABASE_POOL_SIZE=50
DATABASE_MAX_OVERFLOW=100

# Redis (use persistence)
REDIS_URL=redis://prod-redis:6379/0

# Security
SECRET_KEY=<generate-strong-random-key>
ALLOWED_ORIGINS=https://yourdomain.com,https://api.yourdomain.com

# Telegram
TELEGRAM_BOT_TOKEN=<production-bot-token>
TELEGRAM_USE_WEBHOOK=True
TELEGRAM_WEBHOOK_URL=https://api.yourdomain.com/webhook

# Business Logic
DRIVER_SEARCH_RADIUS_KM=15
ORDER_TIMEOUT_SECONDS=600
```

## Database Optimization

### PostgreSQL Configuration

```sql
-- Create indexes
CREATE INDEX CONCURRENTLY idx_orders_status_created ON orders(status, created_at);
CREATE INDEX CONCURRENTLY idx_drivers_available_location ON drivers(is_available, current_latitude, current_longitude);
CREATE INDEX CONCURRENTLY idx_trips_driver_date ON trips(driver_id, started_at);

-- Connection pooling settings
ALTER SYSTEM SET max_connections = 200;
ALTER SYSTEM SET shared_buffers = '2GB';
ALTER SYSTEM SET effective_cache_size = '6GB';
ALTER SYSTEM SET maintenance_work_mem = '512MB';
ALTER SYSTEM SET checkpoint_completion_target = 0.9;
ALTER SYSTEM SET wal_buffers = '16MB';
ALTER SYSTEM SET default_statistics_target = 100;
ALTER SYSTEM SET random_page_cost = 1.1;
```

## Monitoring Setup

### Prometheus + Grafana

```yaml
# prometheus.yml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'taxi-backend'
    static_configs:
      - targets: ['backend:8000']
```

### Application Metrics

Add to `app/main.py`:

```python
from prometheus_fastapi_instrumentator import Instrumentator

@app.on_event("startup")
async def startup():
    Instrumentator().instrument(app).expose(app)
```

## Backup Strategy

### Database Backups

```bash
# Daily backup script
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR=/backups
mkdir -p $BACKUP_DIR

pg_dump -h $DB_HOST -U $DB_USER $DB_NAME | gzip > $BACKUP_DIR/backup_$DATE.sql.gz

# Keep last 30 days
find $BACKUP_DIR -type f -mtime +30 -delete
```

### Automated Backups (AWS)

```bash
# Enable automated backups
aws rds modify-db-instance \
  --db-instance-identifier taxi-db \
  --backup-retention-period 7 \
  --preferred-backup-window "03:00-04:00"
```

## Scaling Guidelines

### Horizontal Scaling

```bash
# Scale API service
docker-compose up -d --scale backend=5

# Or with Kubernetes
kubectl scale deployment taxi-backend --replicas=5
```

### Database Scaling

1. **Read Replicas**: For read-heavy workloads
2. **Connection Pooling**: PgBouncer or Pgpool-II
3. **Partitioning**: For large tables (trips, orders)

### Redis Scaling

1. **Redis Cluster**: For high availability
2. **Sentinel**: For automatic failover
3. **Separate Instances**: Cache vs Queue

## Performance Optimization

### API Performance

```python
# Add caching decorator
from app.core.redis import redis_client

async def cached(key: str, ttl: int = 300):
    async def decorator(func):
        async def wrapper(*args, **kwargs):
            cached_value = await redis_client.get(key)
            if cached_value:
                return cached_value
            
            result = await func(*args, **kwargs)
            await redis_client.set(key, result, ttl)
            return result
        return wrapper
    return decorator
```

### Database Query Optimization

```python
# Use selectinload for eager loading
from sqlalchemy.orm import selectinload

query = select(Order).options(
    selectinload(Order.user),
    selectinload(Order.driver)
)
```

## Health Checks

### Kubernetes Liveness/Readiness Probes

```yaml
apiVersion: v1
kind: Pod
spec:
  containers:
  - name: backend
    livenessProbe:
      httpGet:
        path: /health
        port: 8000
      initialDelaySeconds: 30
      periodSeconds: 10
    readinessProbe:
      httpGet:
        path: /health
        port: 8000
      initialDelaySeconds: 5
      periodSeconds: 5
```

## Security Hardening

### API Security

```python
# Add rate limiting
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@app.get("/api/v1/orders/")
@limiter.limit("100/minute")
async def get_orders():
    pass
```

### Database Security

```sql
-- Create read-only user for analytics
CREATE USER analytics_user WITH PASSWORD 'secure_password';
GRANT CONNECT ON DATABASE taxi_db TO analytics_user;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO analytics_user;

-- Enable row-level security
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;
CREATE POLICY user_orders ON orders FOR SELECT USING (user_id = current_user_id());
```

## Disaster Recovery

### Recovery Time Objective (RTO): 1 hour
### Recovery Point Objective (RPO): 15 minutes

1. **Automated Backups**: Every 15 minutes
2. **Hot Standby**: Secondary database in different region
3. **Runbook**: Documented recovery procedures
4. **Regular DR Drills**: Monthly testing

## Compliance

### GDPR Compliance

```python
# Data deletion endpoint
@app.delete("/api/v1/users/{user_id}/gdpr")
async def delete_user_data(user_id: int):
    # Delete all user data
    await delete_user_orders(user_id)
    await delete_user_trips(user_id)
    await delete_user_ratings(user_id)
    await delete_user(user_id)
    return {"status": "deleted"}
```

### Audit Logging

```python
# Log all sensitive operations
logger.info(
    "user_data_accessed",
    user_id=user_id,
    accessed_by=admin_id,
    ip_address=request.client.host
)
```

## Cost Optimization

1. **Auto-scaling**: Scale down during low-traffic periods
2. **Reserved Instances**: For predictable workloads
3. **Spot Instances**: For non-critical batch jobs
4. **Database Optimization**: Remove unused indexes, vacuum regularly
5. **CDN**: For static assets
6. **Compression**: Enable gzip/brotli

## Maintenance Windows

- **Scheduled**: Every Sunday 2:00-4:00 AM UTC
- **Emergency**: On-demand with 1-hour notice
- **Zero-downtime**: Blue-green deployment strategy

## Support & Monitoring

- **On-call**: 24/7 rotation
- **Alerting**: PagerDuty/Opsgenie
- **Incident Response**: Max 15 minutes
- **Post-mortems**: Within 48 hours of incidents
