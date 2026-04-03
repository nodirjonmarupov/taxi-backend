# API Testing Examples

## Postman Collection

### Environment Variables
```json
{
  "base_url": "http://localhost:8000",
  "api_version": "v1"
}
```

## cURL Examples

### 1. Create User

```bash
curl -X POST "http://localhost:8000/api/v1/users/" \
  -H "Content-Type: application/json" \
  -d '{
    "telegram_id": "123456789",
    "username": "john_doe",
    "first_name": "John",
    "last_name": "Doe",
    "phone": "+1234567890",
    "role": "user"
  }'
```

Response:
```json
{
  "id": 1,
  "telegram_id": "123456789",
  "username": "john_doe",
  "first_name": "John",
  "last_name": "Doe",
  "phone": "+1234567890",
  "role": "user",
  "is_active": true,
  "created_at": "2024-02-08T10:30:00"
}
```

### 2. Create Driver Profile

```bash
curl -X POST "http://localhost:8000/api/v1/drivers/" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": 2,
    "car_model": "Toyota Camry",
    "car_number": "ABC-123",
    "car_color": "Black",
    "license_number": "DL12345"
  }'
```

### 3. Update Driver Location

```bash
curl -X POST "http://localhost:8000/api/v1/drivers/1/location" \
  -H "Content-Type: application/json" \
  -d '{
    "latitude": 40.7128,
    "longitude": -74.0060
  }'
```

### 4. Set Driver Online

```bash
curl -X POST "http://localhost:8000/api/v1/drivers/1/availability?is_available=true" \
  -H "Content-Type: application/json"
```

### 5. Create Order

```bash
curl -X POST "http://localhost:8000/api/v1/orders/?user_id=1" \
  -H "Content-Type: application/json" \
  -d '{
    "pickup_latitude": 40.7128,
    "pickup_longitude": -74.0060,
    "pickup_address": "Times Square, New York",
    "destination_latitude": 40.7580,
    "destination_longitude": -73.9855,
    "destination_address": "Central Park, New York",
    "notes": "Please call when you arrive"
  }'
```

Response:
```json
{
  "id": 1,
  "user_id": 1,
  "driver_id": null,
  "pickup_latitude": 40.7128,
  "pickup_longitude": -74.006,
  "pickup_address": "Times Square, New York",
  "destination_latitude": 40.758,
  "destination_longitude": -73.9855,
  "destination_address": "Central Park, New York",
  "status": "pending",
  "estimated_price": 15.75,
  "notes": "Please call when you arrive",
  "created_at": "2024-02-08T10:35:00",
  "accepted_at": null,
  "started_at": null,
  "completed_at": null
}
```

### 6. Accept Order (Driver)

```bash
curl -X POST "http://localhost:8000/api/v1/orders/1/accept?driver_id=1" \
  -H "Content-Type: application/json"
```

### 7. Start Trip

```bash
curl -X POST "http://localhost:8000/api/v1/orders/1/start" \
  -H "Content-Type: application/json"
```

### 8. Create Trip Record

```bash
curl -X POST "http://localhost:8000/api/v1/trips/" \
  -H "Content-Type: application/json" \
  -d '{
    "order_id": 1,
    "driver_id": 1,
    "start_latitude": 40.7128,
    "start_longitude": -74.0060
  }'
```

### 9. End Trip

```bash
curl -X POST "http://localhost:8000/api/v1/trips/1/end" \
  -H "Content-Type: application/json" \
  -d '{
    "end_latitude": 40.7580,
    "end_longitude": -73.9855
  }'
```

Response:
```json
{
  "id": 1,
  "order_id": 1,
  "driver_id": 1,
  "start_latitude": 40.7128,
  "start_longitude": -74.006,
  "end_latitude": 40.758,
  "end_longitude": -73.9855,
  "distance_km": 5.85,
  "duration_seconds": 1200,
  "total_price": 9.52,
  "commission": 1.90,
  "driver_earnings": 7.62,
  "started_at": "2024-02-08T10:40:00",
  "ended_at": "2024-02-08T11:00:00"
}
```

### 10. Rate Trip

```bash
curl -X POST "http://localhost:8000/api/v1/trips/1/rate?user_id=1" \
  -H "Content-Type: application/json" \
  -d '{
    "trip_id": 1,
    "rating": 5,
    "comment": "Great driver, smooth ride!"
  }'
```

### 11. Get Driver Stats

```bash
curl "http://localhost:8000/api/v1/drivers/1/stats"
```

Response:
```json
{
  "total_trips": 42,
  "total_earnings": 450.25,
  "average_rating": 4.8,
  "today_trips": 5,
  "today_earnings": 52.30
}
```

### 12. Get User Orders

```bash
curl "http://localhost:8000/api/v1/orders/user/1?skip=0&limit=10"
```

### 13. Get Admin Stats

```bash
curl "http://localhost:8000/api/v1/admin/stats"
```

Response:
```json
{
  "total_users": 150,
  "total_drivers": 45,
  "active_drivers": 12,
  "total_orders": 500,
  "pending_orders": 3,
  "active_trips": 8,
  "total_revenue": 5250.75,
  "total_commission": 1050.15
}
```

## Python Testing Examples

### Using httpx

```python
import httpx
import asyncio

async def test_complete_flow():
    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        # 1. Create user
        user_response = await client.post(
            "/api/v1/users/",
            json={
                "telegram_id": "987654321",
                "first_name": "Jane",
                "last_name": "Smith",
                "role": "user"
            }
        )
        user = user_response.json()
        user_id = user["id"]
        print(f"Created user: {user_id}")
        
        # 2. Create driver
        driver_user_response = await client.post(
            "/api/v1/users/",
            json={
                "telegram_id": "111222333",
                "first_name": "Bob",
                "last_name": "Driver",
                "role": "driver"
            }
        )
        driver_user = driver_user_response.json()
        
        driver_response = await client.post(
            "/api/v1/drivers/",
            json={
                "user_id": driver_user["id"],
                "car_model": "Honda Accord",
                "car_number": "XYZ-789"
            }
        )
        driver = driver_response.json()
        driver_id = driver["id"]
        print(f"Created driver: {driver_id}")
        
        # 3. Set driver location and online
        await client.post(
            f"/api/v1/drivers/{driver_id}/location",
            json={
                "latitude": 40.7128,
                "longitude": -74.0060
            }
        )
        
        await client.post(
            f"/api/v1/drivers/{driver_id}/availability",
            params={"is_available": True}
        )
        print("Driver is online")
        
        # 4. Create order
        order_response = await client.post(
            f"/api/v1/orders/",
            params={"user_id": user_id},
            json={
                "pickup_latitude": 40.7128,
                "pickup_longitude": -74.0060,
                "destination_latitude": 40.7580,
                "destination_longitude": -73.9855
            }
        )
        order = order_response.json()
        order_id = order["id"]
        print(f"Created order: {order_id}")
        
        # 5. Accept order
        await client.post(
            f"/api/v1/orders/{order_id}/accept",
            params={"driver_id": driver_id}
        )
        print("Order accepted")
        
        # 6. Start trip
        trip_response = await client.post(
            "/api/v1/trips/",
            json={
                "order_id": order_id,
                "driver_id": driver_id,
                "start_latitude": 40.7128,
                "start_longitude": -74.0060
            }
        )
        trip = trip_response.json()
        trip_id = trip["id"]
        print(f"Trip started: {trip_id}")
        
        # 7. End trip
        end_response = await client.post(
            f"/api/v1/trips/{trip_id}/end",
            json={
                "end_latitude": 40.7580,
                "end_longitude": -73.9855
            }
        )
        completed_trip = end_response.json()
        print(f"Trip completed: ${completed_trip['total_price']}")
        
        # 8. Rate trip
        await client.post(
            f"/api/v1/trips/{trip_id}/rate",
            params={"user_id": user_id},
            json={
                "trip_id": trip_id,
                "rating": 5,
                "comment": "Excellent service!"
            }
        )
        print("Trip rated")
        
        # 9. Get driver stats
        stats_response = await client.get(f"/api/v1/drivers/{driver_id}/stats")
        stats = stats_response.json()
        print(f"Driver earnings: ${stats['total_earnings']}")

if __name__ == "__main__":
    asyncio.run(test_complete_flow())
```

## Load Testing with Locust

### locustfile.py

```python
from locust import HttpUser, task, between

class TaxiUser(HttpUser):
    wait_time = between(1, 3)
    
    def on_start(self):
        # Create user
        response = self.client.post("/api/v1/users/", json={
            "telegram_id": f"user_{self.user_id}",
            "first_name": "Test",
            "last_name": "User",
            "role": "user"
        })
        self.user_id = response.json()["id"]
    
    @task(3)
    def create_order(self):
        self.client.post(f"/api/v1/orders/?user_id={self.user_id}", json={
            "pickup_latitude": 40.7128,
            "pickup_longitude": -74.0060,
            "destination_latitude": 40.7580,
            "destination_longitude": -73.9855
        })
    
    @task(2)
    def get_orders(self):
        self.client.get(f"/api/v1/orders/user/{self.user_id}")
    
    @task(1)
    def get_stats(self):
        self.client.get("/api/v1/admin/stats")

class TaxiDriver(HttpUser):
    wait_time = between(2, 5)
    
    def on_start(self):
        # Create driver
        user_response = self.client.post("/api/v1/users/", json={
            "telegram_id": f"driver_{self.user_id}",
            "first_name": "Test",
            "last_name": "Driver",
            "role": "driver"
        })
        user_id = user_response.json()["id"]
        
        driver_response = self.client.post("/api/v1/drivers/", json={
            "user_id": user_id,
            "car_model": "Test Car",
            "car_number": "TEST123"
        })
        self.driver_id = driver_response.json()["id"]
    
    @task
    def update_location(self):
        self.client.post(f"/api/v1/drivers/{self.driver_id}/location", json={
            "latitude": 40.7128 + (hash(self.user_id) % 100) / 1000,
            "longitude": -74.0060 + (hash(self.user_id) % 100) / 1000
        })
```

Run:
```bash
locust -f locustfile.py --host=http://localhost:8000
```

## Performance Benchmarks

### Expected Response Times (p95)

- Health check: < 10ms
- Create user: < 50ms
- Create order: < 100ms
- Driver matching: < 200ms
- Get stats: < 100ms
- List orders: < 150ms

### Throughput Targets

- Requests/second: 1000+
- Concurrent users: 10,000+
- Orders/minute: 500+
