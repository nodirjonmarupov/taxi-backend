"""
Payme Subscribe API Service
"""
import base64
import httpx
from typing import Optional, Dict, Any

from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)


class PaymeError(Exception):
    """Payme API xatolari"""
    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message
        super().__init__(f"Payme Error {code}: {message}")


class PaymeService:
    """Payme Subscribe API Service"""
    
    def __init__(self):
        self.merchant_id = settings.PAYME_MERCHANT_ID
        self.secret_key = settings.PAYME_SECRET_KEY
        self.api_url = settings.PAYME_API_URL
        self.timeout = settings.PAYME_TIMEOUT
        
        # Base64 AUTH
        auth_string = f"{self.merchant_id}:{self.secret_key}"
        self.auth_header = base64.b64encode(auth_string.encode()).decode()
    
    async def _request(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Payme API'ga so'rov yuborish"""
        headers = {
            "Authorization": f"Basic {self.auth_header}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params
        }
        
        logger.info(f"📤 Payme request: {method}")
        logger.debug(f"Payload: {payload}")
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.api_url,
                    json=payload,
                    headers=headers
                )
                
                response.raise_for_status()
                data = response.json()
                
                logger.debug(f"📥 Payme response: {data}")
                
                if "error" in data:
                    error = data["error"]
                    logger.error(f"Payme API xato: {error}")
                    raise PaymeError(
                        code=error.get("code", -1),
                        message=error.get("message", "Unknown error")
                    )
                
                return data.get("result", {})
                
        except httpx.HTTPError as e:
            logger.error(f"HTTP xato: {e}")
            raise PaymeError(code=-1, message=f"HTTP Error: {str(e)}")
        except Exception as e:
            logger.error(f"Payme request xato: {e}")
            raise PaymeError(code=-1, message=str(e))
    
    async def create_card(self, card_number: str, expire: str) -> Dict[str, Any]:
        """
        Kartani ro'yxatdan o'tkazish (1-qadam)
        
        Args:
            card_number: 16 raqamli karta raqami
            expire: MMYY formatida amal qilish muddati
        
        Returns:
            {
                "token": "temporary_token",
                "phone": "+998901234567"
            }
        """
        try:
            result = await self._request(
                method="cards.create",
                params={
                    "card": {
                        "number": card_number,
                        "expire": expire
                    }
                }
            )
            
            logger.info(f"✅ Karta yaratildi: token={result.get('card', {}).get('token')}")
            
            return {
                "token": result.get("card", {}).get("token"),
                "phone": result.get("card", {}).get("phone", "")
            }
            
        except PaymeError:
            raise
        except Exception as e:
            logger.error(f"Create card xato: {e}")
            raise PaymeError(code=-1, message=f"Karta yaratishda xato: {str(e)}")
    
    async def verify_card(self, token: str, code: str) -> str:
        """
        Kartani tasdiqlash (2-qadam)
        
        Args:
            token: Temporary token (create_card dan)
            code: SMS kod
        
        Returns:
            card_token: Doimiy token
        """
        try:
            result = await self._request(
                method="cards.verify",
                params={
                    "token": token,
                    "code": code
                }
            )
            
            card_token = result.get("card", {}).get("token")
            
            logger.info(f"✅ Karta tasdiqlandi: {card_token}")
            
            return card_token
            
        except PaymeError:
            raise
        except Exception as e:
            logger.error(f"Verify card xato: {e}")
            raise PaymeError(code=-1, message=f"Tasdiqlashda xato: {str(e)}")
    
    async def check_card(self, card_token: str) -> bool:
        """
        Kartani tekshirish
        
        Args:
            card_token: Karta tokeni
        
        Returns:
            True agar karta faol
        """
        try:
            result = await self._request(
                method="cards.check",
                params={
                    "token": card_token
                }
            )
            
            logger.info(f"✅ Karta tekshirildi: {result}")
            return True
            
        except PaymeError:
            return False
        except Exception as e:
            logger.error(f"Check card xato: {e}")
            return False
    
    async def pay_commission(
        self, 
        card_token: str, 
        amount_tiyin: int,
        driver_id: int,
        order_id: int
    ) -> Dict[str, Any]:
        """
        Komissiya to'lash
        
        Args:
            card_token: Karta tokeni
            amount_tiyin: Summa (tiyin'da, 1 so'm = 100 tiyin)
            driver_id: Driver ID
            order_id: Order ID
        
        Returns:
            {
                "transaction_id": "...",
                "state": 2
            }
        """
        try:
            # 1. Receipt yaratish
            receipt_result = await self._request(
                method="receipts.create",
                params={
                    "amount": amount_tiyin,
                    "account": {
                        "driver_id": driver_id,
                        "order_id": order_id
                    }
                }
            )
            
            receipt_id = receipt_result.get("receipt", {}).get("_id")
            
            logger.info(f"✅ Receipt yaratildi: {receipt_id}")
            
            # 2. To'lovni amalga oshirish
            pay_result = await self._request(
                method="receipts.pay",
                params={
                    "id": receipt_id,
                    "token": card_token
                }
            )
            
            logger.info(f"✅ To'lov amalga oshirildi: {pay_result}")
            
            return {
                "transaction_id": pay_result.get("receipt", {}).get("_id"),
                "state": pay_result.get("receipt", {}).get("state", 0)
            }
            
        except PaymeError:
            raise
        except Exception as e:
            logger.error(f"Pay commission xato: {e}")
            raise PaymeError(code=-1, message=f"To'lovda xato: {str(e)}")

# payme_service.py ga qo'shing (test uchun)

class MockPaymeService:
    """Test uchun mock service"""
    
    async def create_card(self, card_number: str, expire: str):
        logger.info("🧪 MOCK: Karta yaratilmoqda...")
        return {
            "token": "mock_temp_token_12345",
            "phone": "+998901234567"
        }
    
    async def verify_card(self, token: str, code: str):
        logger.info("🧪 MOCK: Karta tasdiqlanmoqda...")
        return "mock_card_token_67890"

# Real yoki mock tanlash
if settings.PAYME_MERCHANT_ID == "test":
    payme_service = MockPaymeService()
else:
    payme_service = PaymeService()

# Global instance
payme_service = PaymeService()