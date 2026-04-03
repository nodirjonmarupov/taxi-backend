"""
User CRUD operations
"""
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models.user import User, Driver
from app.schemas.user import UserCreate


class UserCRUD:
    """User CRUD operations"""
    
    @staticmethod
    async def create(db: AsyncSession, user: UserCreate) -> User:
        """User yaratish"""
        db_user = User(
            telegram_id=user.telegram_id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            role=user.role
        )
        db.add(db_user)
        await db.commit()
        await db.refresh(db_user)
        return db_user
    
    @staticmethod
    async def get_by_id(db: AsyncSession, user_id: int) -> Optional[User]:
        """ID bo'yicha olish"""
        result = await db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_by_telegram_id(db: AsyncSession, telegram_id: int) -> Optional[User]:
        """Telegram ID bo'yicha olish"""
        result = await db.execute(select(User).where(User.telegram_id == telegram_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_phone(db: AsyncSession, phone: str) -> Optional[User]:
        """Telefon raqam bo'yicha olish"""
        result = await db.execute(select(User).where(User.phone == phone))
        return result.scalar_one_or_none()

    @staticmethod
    async def update_language(db: AsyncSession, user_id: int, language_code: str) -> Optional[User]:
        """Foydalanuvchi tilini yangilash"""
        user = await UserCRUD.get_by_id(db, user_id)
        if not user:
            return None
        user.language_code = language_code
        await db.commit()
        await db.refresh(user)
        return user


class DriverCRUD:
    """Driver CRUD operations"""
    
    @staticmethod
    async def get_by_id(db: AsyncSession, driver_id: int) -> Optional[Driver]:
        """ID bo'yicha olish"""
        result = await db.execute(select(Driver).where(Driver.id == driver_id))
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_by_user_id(db: AsyncSession, user_id: int) -> Optional[Driver]:
        """User ID bo'yicha olish"""
        result = await db.execute(select(Driver).where(Driver.user_id == user_id))
        return result.scalar_one_or_none()


class RatingCRUD:
    """Rating CRUD operations"""
    
    @staticmethod
    async def create(
        db: AsyncSession, 
        user_id: int, 
        driver_id: int, 
        order_id: int, 
        score: int, 
        comment: str = None
    ):
        """Reyting yaratish"""
        from app.models.user import Rating
        
        rating = Rating(
            user_id=user_id,
            driver_id=driver_id,
            order_id=order_id,
            score=score,
            comment=comment
        )
        
        db.add(rating)
        await db.commit()
        await db.refresh(rating)
        
        # Driver reytingini yangilash
        await RatingCRUD._update_driver_rating(db, driver_id)
        
        return rating
    
    @staticmethod
    async def _update_driver_rating(db: AsyncSession, driver_id: int):
        """Driver reytingini hisoblash"""
        from app.models.user import Rating
        
        result = await db.execute(
            select(func.avg(Rating.score), func.count(Rating.id))
            .where(Rating.driver_id == driver_id)
        )
        
        row = result.first()
        avg_rating = float(row[0]) if row[0] else 5.0
        total_ratings = row[1] or 0
        
        driver = await DriverCRUD.get_by_id(db, driver_id)
        
        if driver:
            driver.rating = round(avg_rating, 2)
            driver.total_ratings = total_ratings
            await db.commit()