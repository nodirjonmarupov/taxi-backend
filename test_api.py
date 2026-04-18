"""
API Testing Examples and Usage Guide
Run with: python test_api.py
"""

import requests
import json

from app.core.security import create_access_token

# Base URL
BASE_URL = "http://localhost:8000/api/v1"


class TaxiAPITester:
    """API testing helper class."""
    
    def __init__(self, base_url=BASE_URL):
        self.base_url = base_url
        self.session = requests.Session()

    def set_driver_bearer_auth(self, driver_user_id: int):
        """POST /trips/.../complete uchun JWT (sub = haydovchi user id)."""
        token = create_access_token(data={"sub": str(driver_user_id)})
        self.session.headers["Authorization"] = f"Bearer {token}"
    
    def print_response(self, response, title="Response"):
        """Pretty print API response."""
        print(f"\n{'=' * 60}")
        print(f"{title}")
        print(f"{'=' * 60}")
        print(f"Status: {response.status_code}")
        try:
            print(f"Response:\n{json.dumps(response.json(), indent=2)}")
        except:
            print(f"Response: {response.text}")
        print(f"{'=' * 60}\n")
    
    # ==================== USER ENDPOINTS ====================
    
    def create_user(self, telegram_id, first_name, phone=None):
        """Create a new user."""
        payload = {
            "telegram_id": telegram_id,
            "first_name": first_name,
            "phone": phone,
            "role": "user"
        }
        response = self.session.post(f"{self.base_url}/users", json=payload)
        self.print_response(response, "Create User")
        return response.json() if response.status_code == 201 else None
    
    def get_user(self, user_id):
        """Get user by ID."""
        response = self.session.get(f"{self.base_url}/users/{user_id}")
        self.print_response(response, f"Get User {user_id}")
        return response.json() if response.status_code == 200 else None
    
    def get_user_by_telegram(self, telegram_id):
        """Get user by Telegram ID."""
        response = self.session.get(f"{self.base_url}/users/telegram/{telegram_id}")
        self.print_response(response, f"Get User by Telegram {telegram_id}")
        return response.json() if response.status_code == 200 else None
    
    # ==================== DRIVER ENDPOINTS ====================
    
    def create_driver(self, user_id, car_number, car_model="Toyota Camry", car_color="Black"):
        """Register a new driver."""
        payload = {
            "user_id": user_id,
            "car_number": car_number,
            "car_model": car_model,
            "car_color": car_color
        }
        response = self.session.post(f"{self.base_url}/drivers", json=payload)
        self.print_response(response, "Create Driver")
        return response.json() if response.status_code == 201 else None
    
    def update_driver_location(self, driver_id, latitude, longitude):
        """Update driver's location."""
        payload = {
            "latitude": latitude,
            "longitude": longitude
        }
        response = self.session.post(
            f"{self.base_url}/drivers/{driver_id}/location",
            json=payload
        )
        self.print_response(response, f"Update Driver {driver_id} Location")
        return response.json() if response.status_code == 200 else None
    
    def get_driver_stats(self, driver_id):
        """Get driver statistics."""
        response = self.session.get(f"{self.base_url}/drivers/{driver_id}/stats")
        self.print_response(response, f"Driver {driver_id} Stats")
        return response.json() if response.status_code == 200 else None
    
    # ==================== ORDER ENDPOINTS ====================
    
    def create_order(self, user_id, pickup_lat, pickup_lon, dest_lat=None, dest_lon=None):
        """Create a new taxi order."""
        payload = {
            "pickup_latitude": pickup_lat,
            "pickup_longitude": pickup_lon
        }
        if dest_lat and dest_lon:
            payload["destination_latitude"] = dest_lat
            payload["destination_longitude"] = dest_lon
        
        response = self.session.post(
            f"{self.base_url}/orders?user_id={user_id}",
            json=payload
        )
        self.print_response(response, "Create Order")
        return response.json() if response.status_code == 201 else None
    
    def get_order(self, order_id):
        """Get order details."""
        response = self.session.get(f"{self.base_url}/orders/{order_id}")
        self.print_response(response, f"Get Order {order_id}")
        return response.json() if response.status_code == 200 else None
    
    def accept_order(self, order_id):
        """Driver accepts an order (Bearer: set_driver_bearer_auth)."""
        response = self.session.post(
            f"{self.base_url}/orders/{order_id}/accept",
        )
        self.print_response(response, f"Accept Order {order_id}")
        return response.json() if response.status_code == 200 else None
    
    # ==================== TRIP ENDPOINTS ====================
    
    def start_trip(self, order_id):
        """Start a trip (Bearer: set_driver_bearer_auth)."""
        response = self.session.post(
            f"{self.base_url}/trips/{order_id}/start",
        )
        self.print_response(response, "Start Trip")
        return response.json() if response.status_code == 200 else None
    
    def complete_trip(self, order_id):
        """Complete a trip — yakuniy narx serverda hisoblanadi (Bearer: set_driver_bearer_auth)."""
        response = self.session.post(
            f"{self.base_url}/trips/{order_id}/complete",
            json={},
        )
        self.print_response(response, f"Complete Trip {order_id}")
        return response.json() if response.status_code == 200 else None
    
    def estimate_trip_price(self, pickup_lat, pickup_lon, dest_lat, dest_lon):
        """Estimate trip price."""
        response = self.session.get(
            f"{self.base_url}/trips/estimate/price"
            f"?pickup_lat={pickup_lat}&pickup_lon={pickup_lon}"
            f"&dest_lat={dest_lat}&dest_lon={dest_lon}"
        )
        self.print_response(response, "Estimate Price")
        return response.json() if response.status_code == 200 else None
    
    def rate_driver(self, user_id, driver_id, trip_id, score, comment=""):
        """Rate a driver."""
        payload = {
            "trip_id": trip_id,
            "score": score,
            "comment": comment
        }
        response = self.session.post(
            f"{self.base_url}/trips/ratings?user_id={user_id}&driver_id={driver_id}",
            json=payload
        )
        self.print_response(response, "Rate Driver")
        return response.json() if response.status_code == 201 else None
    
    # ==================== ADMIN ENDPOINTS ====================
    
    def get_admin_stats(self):
        """Get platform statistics."""
        response = self.session.get(f"{self.base_url}/admin/stats")
        self.print_response(response, "Admin Stats")
        return response.json() if response.status_code == 200 else None


def run_complete_flow():
    """Run a complete taxi order flow."""
    api = TaxiAPITester()
    
    print("\n🚖 TAXI BACKEND API TEST FLOW")
    print("=" * 60)
    
    # 1. Create User
    print("\n1️⃣  Creating User...")
    user = api.create_user(
        telegram_id=123456789,
        first_name="John Doe",
        phone="+1234567890"
    )
    if not user:
        print("❌ Failed to create user")
        return
    
    # 2. Create Driver
    print("\n2️⃣  Registering Driver...")
    driver_user = api.create_user(
        telegram_id=987654321,
        first_name="Jane Driver",
        phone="+0987654321"
    )
    if not driver_user:
        print("❌ Failed to create driver user")
        return
    
    driver = api.create_driver(
        user_id=driver_user["id"],
        car_number="ABC123",
        car_model="Toyota Prius",
        car_color="White"
    )
    if not driver:
        print("❌ Failed to register driver")
        return
    
    # 3. Update Driver Location
    print("\n3️⃣  Updating Driver Location...")
    api.update_driver_location(
        driver_id=driver["id"],
        latitude=37.7749,
        longitude=-122.4194
    )
    
    # 4. Estimate Trip Price
    print("\n4️⃣  Estimating Trip Price...")
    api.estimate_trip_price(
        pickup_lat=37.7749,
        pickup_lon=-122.4194,
        dest_lat=37.7849,
        dest_lon=-122.4094
    )
    
    # 5. Create Order
    print("\n5️⃣  Creating Order...")
    order = api.create_order(
        user_id=user["id"],
        pickup_lat=37.7749,
        pickup_lon=-122.4194,
        dest_lat=37.7849,
        dest_lon=-122.4094
    )
    if not order:
        print("❌ Failed to create order")
        return
    
    # 6. Check Order Status
    print("\n6️⃣  Checking Order Status...")
    api.get_order(order["id"])

    # Haydovchi JWT — accept / start / complete uchun
    api.set_driver_bearer_auth(driver_user["id"])
    
    # 7. Accept Order (if not auto-assigned)
    if order["status"] == "pending":
        print("\n7️⃣  Driver Accepting Order...")
        api.accept_order(order["id"])
    
    # 8. Start Trip
    print("\n8️⃣  Starting Trip...")
    trip = api.start_trip(order["id"])
    if not trip:
        print("❌ Failed to start trip")
        return
    
    # 9. Complete Trip
    print("\n9️⃣  Completing Trip...")
    completed_trip = api.complete_trip(order_id=trip["id"])
    if not completed_trip:
        print("❌ Failed to complete trip")
        return
    
    # 10. Rate Driver
    print("\n🔟 Rating Driver...")
    api.rate_driver(
        user_id=user["id"],
        driver_id=driver["id"],
        trip_id=trip["id"],
        score=5,
        comment="Great driver, smooth ride!"
    )
    
    # 11. Check Driver Stats
    print("\n1️⃣1️⃣  Checking Driver Stats...")
    api.get_driver_stats(driver["id"])
    
    # 12. Get Admin Stats
    print("\n1️⃣2️⃣  Getting Platform Statistics...")
    api.get_admin_stats()
    
    print("\n✅ COMPLETE FLOW FINISHED SUCCESSFULLY!")
    print("=" * 60)


if __name__ == "__main__":
    print("""
╔══════════════════════════════════════════════════════════╗
║          TAXI BACKEND API TESTING SCRIPT                ║
╚══════════════════════════════════════════════════════════╝

Make sure the backend is running:
  docker-compose up -d
  OR
  python -m app.main

API will be tested at: http://localhost:8000/api/v1

Press Enter to start the test flow...
    """)
    
    input()
    
    try:
        run_complete_flow()
    except Exception as e:
        print(f"\n❌ Error during testing: {e}")
        print("\nMake sure:")
        print("1. Backend is running (docker-compose up -d)")
        print("2. Database is accessible")
        print("3. No port conflicts")
