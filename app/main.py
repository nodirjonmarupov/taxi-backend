"""
Main FastAPI Application - Timgo Taxi Backend
Professional Real-time Taximeter with GPS Tracking
"""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
import json
import time
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException, Response
from fastapi.exceptions import RequestValidationError
from pathlib import Path
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

# Ichki modullar
from app.api.routes import webapp
from app.api.v1 import api_router
from app.core.config import settings
from app.core.database import AsyncSessionLocal, init_db, close_db
from app.core.redis import close_redis
from app.core.logger import get_logger

logger = get_logger(__name__)


# ============================================
# PROFESSIONAL TAXIMETER HTML
# (moved to app/templates/index.html + app/static/main.js)
# ============================================
_TAXIMETER_TEMPLATE = Path(__file__).resolve().parent / "templates" / "index.html"



# ============================================
# USER TRACKING (Haydovchini kuzatish)
# ============================================
USER_TRACKING_HTML = """
<!DOCTYPE html>
<html lang="uz">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
    <meta http-equiv="Pragma" content="no-cache">
    <meta http-equiv="Expires" content="0">
    <title>Taksi yetib kelmoqda</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0a0a0a; color: #fff; }
        #map { width: 100%; height: 100vh; }
        .info-panel {
            position: absolute; top: 20px; left: 20px; right: 20px;
            background: rgba(0,0,0,0.85); backdrop-filter: blur(12px);
            padding: 16px; border-radius: 16px; box-shadow: 0 4px 20px rgba(0,0,0,0.3);
            z-index: 1000; border: 1px solid rgba(255,255,255,0.1);
        }
        .status-text { font-size: 18px; font-weight: bold; margin-bottom: 6px; color: #276EF1; }
        .car-info { color: rgba(255,255,255,0.7); font-size: 14px; margin-bottom: 8px; }
        .eta { font-size: 24px; color: #276EF1; font-weight: bold; }
        .user-dot {
            width: 28px; height: 28px; background: #276EF1; border-radius: 50%;
            border: 4px solid white;
            box-shadow: 0 0 0 6px rgba(39,110,241,0.35), 0 4px 12px rgba(0,0,0,0.3);
            animation: pulse 1.5s ease-in-out infinite;
        }
        @keyframes pulse { 0%,100% { transform:scale(1);opacity:1; } 50% { transform:scale(1.15);opacity:.85; } }
        .btn-recenter { position:fixed; bottom:20px; right:20px; z-index:1000; padding:12px 18px; border-radius:12px; border:none; background:rgba(39,110,241,0.95); color:#fff; font-weight:600; cursor:pointer; box-shadow:0 2px 12px rgba(0,0,0,0.3); }
        .driver-marker-inner {
            width:48px; height:48px; background:#276EF1; border-radius:50%;
            border:3px solid white; box-shadow:0 4px 16px rgba(0,0,0,0.4);
            display:flex; align-items:center; justify-content:center;
            font-size:26px; line-height:1; transform-origin:center center; will-change:transform;
        }
    </style>
</head>
<body>
    <div id="map"></div>
    <div class="info-panel">
        <div class="status-text" id="statusText">Haydovchi yo&#39;lda</div>
        <div class="car-info" id="carInfo">—</div>
        <div class="eta" id="eta">— daqiqa</div>
    </div>
    <button class="btn-recenter" id="btnRecenter">📍 Haydovchi</button>
    <script>
        /* ── Dynamic resource loader: MapLibre + kesh o'ldirish ── */
        (function() {
            var _V = Date.now();
            var _css = document.createElement('link');
            _css.rel = 'stylesheet';
            _css.href = 'https://cdn.jsdelivr.net/npm/maplibre-gl@3.6.2/dist/maplibre-gl.css?v=' + _V;
            document.head.appendChild(_css);
            var _tg = document.createElement('script');
            _tg.src = 'https://telegram.org/js/telegram-web-app.js?v=' + _V;
            document.head.appendChild(_tg);
            var _ml = document.createElement('script');
            _ml.src = 'https://cdn.jsdelivr.net/npm/maplibre-gl@3.6.2/dist/maplibre-gl.js?v=' + _V;
            _ml.onload = function() { init(); };
            document.head.appendChild(_ml);
        })();

        /* ── State ── */
        var map, driverMarker, driverMarkerInnerEl, userMarker, pickupMarker;
        var urlParams = new URLSearchParams(window.location.search);
        var orderId = urlParams.get('order_id');
        var API_BASE = window.location.origin;
        var userLocation = null;
        var liveUserLocation = null;
        var POLL_MS = 5000;
        var LERP_MS = 4500;
        var AVG_KMH = 40;
        var followDriver = true;
        var displayLat = null, displayLon = null;
        var lerpFromLat, lerpFromLon, lerpToLat, lerpToLon;
        var lerpStartTs = 0;
        var prevDispLat = null, prevDispLon = null;
        var smoothBearing = 0, targetBearing = 0;
        var smoothMapBearing = 0, smoothMapPitch = 0;
        var rafId = null;
        var lastUserInteractMs = 0;
        var IDLE_FOLLOW_MS = 10000;
        var ignoreInteractionUntilMs = 0;
        var cameraProgrammatic = false;
        var NAV_PITCH_DEG = 45;
        var NAV_3D_DISTANCE_KM = 0.8;

        function isValid(lat, lon) {
            return lat != null && lon != null && !isNaN(lat) && !isNaN(lon)
                && lat >= -90 && lat <= 90 && lon >= -180 && lon <= 180;
        }
        function lerp(a, b, t) { return a + (b - a) * t; }
        function lerpAngle(a, b, t) {
            var d = ((((b - a) % 360) + 540) % 360) - 180;
            return a + d * t;
        }
        function easeOut(t) { return 1 - Math.pow(1 - t, 3); }
        function haversineKm(aLat, aLon, bLat, bLon) {
            var R = 6371, toRad = Math.PI / 180;
            var dLat = (bLat - aLat) * toRad, dLon = (bLon - aLon) * toRad;
            var a = Math.sin(dLat/2)*Math.sin(dLat/2)
                  + Math.cos(aLat*toRad)*Math.cos(bLat*toRad)*Math.sin(dLon/2)*Math.sin(dLon/2);
            return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
        }
        function bearingDeg(fromLat, fromLon, toLat, toLon) {
            var toRad = Math.PI / 180, toDeg = 180 / Math.PI;
            var dLon = (toLon - fromLon) * toRad;
            var y = Math.sin(dLon) * Math.cos(toLat * toRad);
            var x = Math.cos(fromLat * toRad) * Math.sin(toLat * toRad)
                  - Math.sin(fromLat * toRad) * Math.cos(toLat * toRad) * Math.cos(dLon);
            return (Math.atan2(y, x) * toDeg + 360) % 360;
        }

        /* ── Lerp target yangilash ── */
        function beginLerpTo(lon, lat) {
            if (displayLat == null || displayLon == null) {
                displayLat = lat; displayLon = lon;
                lerpFromLat = lat; lerpFromLon = lon;
                lerpToLat = lat; lerpToLon = lon;
                lerpStartTs = performance.now();
                if (driverMarker) driverMarker.setLngLat([lon, lat]);
                return;
            }
            lerpFromLat = displayLat; lerpFromLon = displayLon;
            lerpToLat = lat; lerpToLon = lon;
            lerpStartTs = performance.now();
        }

        /* ── Kamera ── */
        function onUserMapInteraction() {
            if (performance.now() < ignoreInteractionUntilMs) return;
            if (cameraProgrammatic) return;
            followDriver = false;
            lastUserInteractMs = performance.now();
        }
        function wireInteractionHandlers() {
            if (!map) return;
            map.on('dragstart', onUserMapInteraction);
            map.on('zoomstart', onUserMapInteraction);
            map.on('rotatestart', function(e) { if (e && e.originalEvent) onUserMapInteraction(); });
        }
        function easeFollowToDriver() {
            if (!map || displayLat == null) return;
            cameraProgrammatic = true;
            map.easeTo({ center: [displayLon, displayLat], zoom: 17, pitch: NAV_PITCH_DEG, bearing: smoothBearing, duration: 900 });
            setTimeout(function() {
                try { smoothMapPitch = map.getPitch(); smoothMapBearing = map.getBearing(); } catch (_) {}
                cameraProgrammatic = false;
            }, 950);
        }

        /* ── rAF: animatsiya + kuzatish ── */
        function tickNavFrame(now) {
            if (!map || !driverMarker) { rafId = requestAnimationFrame(tickNavFrame); return; }
            /* Lerp */
            if (displayLat != null && lerpStartTs > 0) {
                var t = Math.min(1, easeOut((now - lerpStartTs) / LERP_MS));
                displayLat = lerp(lerpFromLat, lerpToLat, t);
                displayLon = lerp(lerpFromLon, lerpToLon, t);
                /* Bearing from movement */
                if (prevDispLat != null) {
                    var km = haversineKm(prevDispLat, prevDispLon, displayLat, displayLon);
                    if (km > 0.000025) targetBearing = bearingDeg(prevDispLat, prevDispLon, displayLat, displayLon);
                }
                smoothBearing = lerpAngle(smoothBearing, targetBearing, 0.14);
                if (driverMarkerInnerEl) driverMarkerInnerEl.style.transform = 'rotate(' + smoothBearing + 'deg)';
                driverMarker.setLngLat([displayLon, displayLat]);
                prevDispLat = displayLat; prevDispLon = displayLon;
            }
            /* Kuzatish (follow) */
            if (followDriver && !cameraProgrammatic && displayLat != null) {
                var ref = liveUserLocation || userLocation;
                var distKm = ref ? haversineKm(displayLat, displayLon, ref.lat, ref.lon) : 999;
                var wantPitch = distKm < NAV_3D_DISTANCE_KM ? NAV_PITCH_DEG : 0;
                smoothMapPitch = lerp(smoothMapPitch, wantPitch, 0.1);
                smoothMapBearing = lerpAngle(smoothMapBearing, smoothBearing, 0.1);
                map.setPitch(smoothMapPitch);
                map.setBearing(smoothMapBearing);
                map.setCenter([displayLon, displayLat]);
            }
            /* 10 s idle → qayta kuzatish */
            if (!followDriver && displayLat != null
                    && performance.now() > ignoreInteractionUntilMs
                    && (performance.now() - lastUserInteractMs) >= IDLE_FOLLOW_MS) {
                followDriver = true;
                easeFollowToDriver();
            }
            rafId = requestAnimationFrame(tickNavFrame);
        }

        /* ── Foydalanuvchi GPS (ixtiyoriy) ── */
        function startUserGeolocation() {
            if (!navigator.geolocation) return;
            var opts = { enableHighAccuracy: true, timeout: 10000, maximumAge: 5000 };
            function onPos(p) {
                var lat = p.coords.latitude, lon = p.coords.longitude;
                if (!isValid(lat, lon)) return;
                liveUserLocation = { lat: lat, lon: lon };
                if (userMarker) userMarker.setLngLat([lon, lat]);
            }
            navigator.geolocation.getCurrentPosition(onPos, function(){}, opts);
            navigator.geolocation.watchPosition(onPos, function(){}, opts);
        }

        /* ── Haydovchi joylashuvini so'rash (polling) ── */
        async function updateDriverLocation() {
            try {
                var r = await fetch(
                    API_BASE + '/api/webapp/order/' + orderId + '/driver-location?v=' + Date.now(),
                    { headers: { 'ngrok-skip-browser-warning': 'true' } }
                );
                var data = await r.json();
                var carEl = document.getElementById('carInfo');
                var etaEl = document.getElementById('eta');
                if (data.driver) {
                    document.getElementById('statusText').textContent = 'Haydovchi yo\\'lda';
                    if (carEl) carEl.textContent = (data.driver.name || 'Haydovchi') + ' \u00b7 ' + (data.driver.car || '\u2014');
                }
                /* snapped_latitude/longitude mavjud bo'lsa — uni olamiz (haydovchi allaqachon snap qilgan) */
                var lat = data.snapped_latitude != null ? data.snapped_latitude : data.latitude;
                var lon = data.snapped_longitude != null ? data.snapped_longitude : data.longitude;
                if (isValid(lat, lon)) {
                    beginLerpTo(lon, lat);
                    var ref = liveUserLocation || userLocation;
                    if (ref && etaEl) {
                        var dKm = haversineKm(lat, lon, ref.lat, ref.lon);
                        etaEl.textContent = Math.max(1, Math.round(dKm / AVG_KMH * 60)) + ' daqiqa';
                    }
                }
            } catch (_) {}
        }

        /* ── init ── */
        async function init() {
            if (!orderId) { document.getElementById('statusText').textContent = 'Order ID topilmadi'; return; }
            try {
                var r = await fetch(API_BASE + '/api/webapp/order/' + orderId + '?v=' + Date.now(),
                    { headers: { 'ngrok-skip-browser-warning': 'true' } });
                if (!r.ok) { document.getElementById('statusText').textContent = 'Buyurtma topilmadi'; return; }
                var order = await r.json();
                userLocation = { lat: order.pickup_latitude, lon: order.pickup_longitude };
                if (!isValid(userLocation.lat, userLocation.lon)) { document.getElementById('statusText').textContent = 'Manzil noto\\'g\\'ri'; return; }
            } catch (_) { document.getElementById('statusText').textContent = 'Xato: buyurtma olinmadi'; return; }

            map = new maplibregl.Map({
                container: 'map',
                style: {
                    version: 8,
                    sources: { osm: { type: 'raster', tileSize: 256, maxzoom: 19,
                        tiles: ['https://a.tile.openstreetmap.org/{z}/{x}/{y}.png',
                                'https://b.tile.openstreetmap.org/{z}/{x}/{y}.png',
                                'https://c.tile.openstreetmap.org/{z}/{x}/{y}.png'] } },
                    layers: [{ id: 'osm', type: 'raster', source: 'osm' }]
                },
                center: [userLocation.lon, userLocation.lat],
                zoom: 16, pitch: 0, bearing: 0, antialias: true
            });

            /* Pickup marker */
            var pickEl = document.createElement('div');
            pickEl.style.cssText = 'width:32px;height:32px;background:#E53E3E;border-radius:50%;border:3px solid white;box-shadow:0 3px 12px rgba(0,0,0,.5)';
            pickupMarker = new maplibregl.Marker({ element: pickEl, anchor: 'center' })
                .setLngLat([userLocation.lon, userLocation.lat]).addTo(map);

            /* User dot */
            var dotEl = document.createElement('div'); dotEl.className = 'user-dot';
            userMarker = new maplibregl.Marker({ element: dotEl, anchor: 'center' })
                .setLngLat([userLocation.lon, userLocation.lat]).addTo(map);

            /* Driver marker */
            var dWrap = document.createElement('div');
            driverMarkerInnerEl = document.createElement('div');
            driverMarkerInnerEl.className = 'driver-marker-inner';
            driverMarkerInnerEl.innerHTML = '🚕';
            dWrap.appendChild(driverMarkerInnerEl);
            driverMarker = new maplibregl.Marker({ element: dWrap, anchor: 'center' })
                .setLngLat([userLocation.lon, userLocation.lat]).addTo(map);

            startUserGeolocation();

            document.getElementById('btnRecenter').onclick = function() {
                followDriver = true; lastUserInteractMs = performance.now();
                easeFollowToDriver();
            };

            map.on('load', function() {
                ignoreInteractionUntilMs = performance.now() + 2500;
                lastUserInteractMs = performance.now();
                smoothMapPitch = map.getPitch(); smoothMapBearing = map.getBearing();
                wireInteractionHandlers();
                updateDriverLocation();
                setInterval(updateDriverLocation, POLL_MS);
                rafId = requestAnimationFrame(tickNavFrame);
            });

            try { var tg = window.Telegram && window.Telegram.WebApp; if (tg) { tg.ready(); tg.expand(); } } catch (_) {}
        }
    </script>
</body>
</html>
"""

# ============================================
# LIFESPAN (Baza va Botni boshqarish)
# ============================================

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    # Security: default-secret ishlatilsa, tokenlarni hisoblab/forge qilish xavfi ortadi.
    if (getattr(settings, "SECRET_KEY", None) or "").strip() == "default-secret":
        logger.warning("⚠️ WARNING: SECRET_KEY is default! Change it for production!")
    # 1. Ma'lumotlar bazasini tekshirish va ustun qo'shish
    async with AsyncSessionLocal() as session:
        try:
            logger.info("🚀 Bazani tekshirish va yangilash boshlandi...")
            await session.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS finished_at TIMESTAMP;"))
            await session.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS final_price NUMERIC(10,2);"))
            await session.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS distance_km DOUBLE PRECISION DEFAULT 0;"))
            await session.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS last_lat DOUBLE PRECISION;"))
            await session.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS last_lon DOUBLE PRECISION;"))
            try:
                await session.execute(text("ALTER TABLE orders ALTER COLUMN distance_km SET DEFAULT 0;"))
            except Exception:
                pass
            try:
                await session.execute(text("UPDATE orders SET distance_km = 0 WHERE distance_km IS NULL;"))
            except Exception:
                pass
            await session.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS is_near_notified BOOLEAN DEFAULT FALSE;"))
            await session.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS arrived_at TIMESTAMP;"))
            await session.execute(
                text(
                    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS user_tracking_message_id INTEGER;"
                )
            )
            await session.execute(
                text(
                    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS commission_deducted_at TIMESTAMP NULL;"
                )
            )
            await session.execute(
                text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS is_bonus_requested BOOLEAN DEFAULT FALSE;")
            )
            await session.execute(
                text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS used_bonus NUMERIC(10,2) DEFAULT 0;")
            )
            await session.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS accepted_at TIMESTAMP;"))
            await session.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS started_at TIMESTAMP;"))
            await session.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS completed_at TIMESTAMP;"))
            await session.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS cancelled_at TIMESTAMP;"))
            await session.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;"))
            # Haydovchi tomonidan yuborilgan snapped koordinatalar (yo'lga yopishtirilgan)
            await session.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS snapped_lat DOUBLE PRECISION;"))
            await session.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS snapped_lon DOUBLE PRECISION;"))
            try:
                await session.execute(text("ALTER TABLE orders ALTER COLUMN updated_at SET DEFAULT CURRENT_TIMESTAMP;"))
            except Exception:
                pass
            try:
                await session.execute(text("ALTER TABLE orders ALTER COLUMN updated_at DROP NOT NULL;"))
            except Exception:
                pass
            # orders.status: PostgreSQL orderstatus ENUM -> VARCHAR(20) (model String(20) bilan moslashtirish)
            try:
                await session.execute(text("ALTER TABLE orders ALTER COLUMN status TYPE VARCHAR(20) USING status::text;"))
            except Exception:
                pass
            # telegram_id: INTEGER -> BIGINT (Telegram ID 2^31 dan oshishi mumkin)
            try:
                await session.execute(text("ALTER TABLE users ALTER COLUMN telegram_id TYPE BIGINT USING telegram_id::BIGINT;"))
            except Exception:
                pass
            await session.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_approved_driver BOOLEAN DEFAULT FALSE;"))
            await session.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;"))
            await session.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_blocked BOOLEAN DEFAULT FALSE;"))
            await session.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT FALSE;"))
            await session.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS bonus_balance NUMERIC(10,2) DEFAULT 0;"))
            await session.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS hashed_password VARCHAR(255);"))
            # ADMIN_IDS dagi telegram_id larni admin qilish
            for aid in getattr(settings, "ADMIN_IDS", []) or []:
                try:
                    await session.execute(text("UPDATE users SET is_admin = TRUE WHERE telegram_id = :tid"), {"tid": aid})
                except Exception:
                    pass
            # settings jadvali (singleton)
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS settings (
                    id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
                    min_price FLOAT NOT NULL DEFAULT 5000,
                    price_per_km FLOAT NOT NULL DEFAULT 2500,
                    commission_rate FLOAT NOT NULL DEFAULT 10.0,
                    surge_multiplier FLOAT NOT NULL DEFAULT 1.5,
                    is_surge_active BOOLEAN NOT NULL DEFAULT FALSE,
                    cashback_percent FLOAT NOT NULL DEFAULT 0,
                    max_bonus_usage_percent FLOAT NOT NULL DEFAULT 0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """))
            await session.execute(text("""
                INSERT INTO settings (id, min_price, price_per_km, commission_rate, surge_multiplier, is_surge_active)
                VALUES (1, 5000, 2500, 10.0, 1.5, FALSE)
                ON CONFLICT (id) DO NOTHING;
            """))

            # Agar settings jadvali oldin yaratilgan bo'lsa, ustunlar yo'qligini ham to'liq yopamiz
            try:
                await session.execute(text("ALTER TABLE settings ADD COLUMN IF NOT EXISTS cashback_percent FLOAT NOT NULL DEFAULT 0;"))
            except Exception:
                pass
            try:
                await session.execute(text("ALTER TABLE settings ADD COLUMN IF NOT EXISTS max_bonus_usage_percent FLOAT NOT NULL DEFAULT 0;"))
            except Exception:
                pass
            try:
                await session.execute(text("ALTER TABLE settings ADD COLUMN IF NOT EXISTS max_bonus_cap FLOAT NOT NULL DEFAULT 5000;"))
            except Exception:
                pass
            try:
                await session.execute(text("ALTER TABLE settings ADD COLUMN IF NOT EXISTS price_per_min_waiting NUMERIC(10,2) NOT NULL DEFAULT 500;"))
            except Exception:
                pass
            # admin_logs
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS admin_logs (
                    id SERIAL PRIMARY KEY,
                    admin_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    action VARCHAR(100) NOT NULL,
                    details JSONB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """))

            # bonus_transactions
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS bonus_transactions (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                    order_id INTEGER REFERENCES orders(id) ON DELETE CASCADE,
                    transaction_type VARCHAR(10) NOT NULL,
                    amount NUMERIC(10,2) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """))
            # promo_codes
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS promo_codes (
                    id SERIAL PRIMARY KEY,
                    code VARCHAR(50) UNIQUE NOT NULL,
                    discount_percent FLOAT,
                    discount_fixed FLOAT,
                    min_order_amount FLOAT,
                    valid_from TIMESTAMP,
                    valid_until TIMESTAMP,
                    max_uses INTEGER,
                    used_count INTEGER DEFAULT 0,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """))
            # drivers jadvaliga modeldagi barcha ustunlarni qo'shish
            for col_def in [
                "status VARCHAR(20) DEFAULT 'pending'",
                "car_year INTEGER",
                "car_photo_id VARCHAR(200)",
                "driver_license_photo_id VARCHAR(200)",
                "is_verified BOOLEAN DEFAULT FALSE",
                "is_available BOOLEAN DEFAULT FALSE",
                "is_active BOOLEAN DEFAULT TRUE",
                "balance NUMERIC(10,2) DEFAULT 0",
                "min_balance_required NUMERIC(10,2) DEFAULT 10000",
                "has_active_card BOOLEAN DEFAULT FALSE",
                "payme_token VARCHAR(255)",
                "rating FLOAT DEFAULT 5.0",
                "total_ratings INTEGER DEFAULT 0",
                "current_latitude FLOAT",
                "current_longitude FLOAT",
                "total_trips INTEGER DEFAULT 0",
                "completed_trips INTEGER DEFAULT 0",
                "total_earnings NUMERIC(12,2) DEFAULT 0",
                "total_commission_paid NUMERIC(12,2) DEFAULT 0",
                "blocked_reason VARCHAR(500)",
                "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            ]:
                try:
                    await session.execute(text(f"ALTER TABLE drivers ADD COLUMN IF NOT EXISTS {col_def};"))
                except Exception:
                    pass

            # Admin uchun individual driver sozlamalari
            await session.execute(text(
                "ALTER TABLE drivers ADD COLUMN IF NOT EXISTS "
                "commission_rate FLOAT DEFAULT NULL;"
            ))
            await session.execute(text(
                "ALTER TABLE drivers ADD COLUMN IF NOT EXISTS "
                "admin_notes TEXT DEFAULT NULL;"
            ))
            # PostgreSQL orderstatus ENUM ga Python modeldagi barcha qiymatlarni qo'shish
            for val in ("pending", "accepted", "in_progress", "completed", "cancelled"):
                try:
                    await session.execute(text(f"ALTER TYPE orderstatus ADD VALUE IF NOT EXISTS '{val}';"))
                except Exception:
                    try:
                        await session.execute(text(
                            f"DO $$ BEGIN ALTER TYPE orderstatus ADD VALUE '{val}'; "
                            "EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
                        ))
                    except Exception:
                        pass
            await session.commit()
            logger.info("✅ Baza muvaffaqiyatli yangilandi.")
        except Exception as e:
            await session.rollback()
            logger.warning(f"⚠️ Bazani yangilashda ogohlantirish: {e}")

    await init_db()

    # 2. Telegram botni ishga tushirish
    from app.bot.telegram_bot import start_bot, stop_bot
    bot_task = asyncio.create_task(start_bot(drop_pending_updates=True))
    logger.info("🤖 Telegram bot ishga tushirildi.")
    
    # 3. Eskirgan buyurtmalarni tozalash (Cleanup)
    cleanup_task = asyncio.create_task(cleanup_expired_orders())
    
    yield
    
    # To'xtatish jarayoni (SIGINT orqali sessiyani to'g'ri yopish)
    bot_task.cancel()
    try:
        await bot_task
    except asyncio.CancelledError:
        pass
    await stop_bot()
    cleanup_task.cancel()
    await close_redis()
    await close_db()
    logger.info("🛑 Ilova resurslari yopildi.")

# ============================================
# APP OBYEKTI VA ROUTERLAR
# ============================================

app = FastAPI(
    title="Timgo Taxi", 
    lifespan=lifespan
)

# Serve /static/main.js and other static assets
_STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

# CORS sozlamalari
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(request, exc: RequestValidationError):
    """422 validation errors — same JSON shape as other API errors."""
    logger.warning(
        "Validation error %s %s: %s",
        request.method,
        request.url.path,
        exc.errors(),
    )
    return JSONResponse(
        status_code=422,
        content={
            "error": True,
            "message": "Validation error",
            "status_code": 422,
            "detail": exc.errors(),
        },
    )


@app.exception_handler(Exception)
async def json_exception_handler(request, exc):
    """Return JSON for unhandled exceptions so admin panel can parse error responses."""
    if isinstance(exc, HTTPException):
        msg = exc.detail if isinstance(exc.detail, str) else "Request error"
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": True,
                "message": msg,
                "status_code": exc.status_code,
                "detail": exc.detail,
            },
        )
    logger.exception(
        "Unhandled exception %s %s: %s",
        request.method,
        request.url.path,
        exc,
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": True,
            "message": "Internal server error",
            "status_code": 500,
            "detail": "Internal server error",
        },
    )


@app.get("/")
async def root():
    return {
        "status": "online",
        "service": "Timgo Taxi",
        "timestamp": datetime.utcnow().isoformat()
    }

@app.get("/taximeter_v2", response_class=HTMLResponse)
async def get_taximeter_v2(order_id: str = "0"):
    base_url = getattr(settings, "WEBAPP_BASE_URL", "https://candid-semiexposed-dung.ngrok-free.dev")
    print(f"[NGROK] Yangilangan WebApp URL: {base_url} | order_id={order_id}")
    # #region agent log
    try:
        import json as _json
        from time import time as _time
        # Write into mounted /app/logs (docker-compose maps ./logs:/app/logs)
        _p = Path(__file__).resolve().parents[2] / "logs" / "debug-2f9a8d.log"
        _payload = {
            "sessionId": "2f9a8d",
            "location": "app/main.py:get_taximeter_v2",
            "message": "Serving taximeter_v2 HTML",
            "data": {
                "order_id": order_id,
                "base_url_len": len(base_url or ""),
                "base_url_has_quote": ("'" in (base_url or "")),
                "base_url_has_newline": ("\n" in (base_url or "")) or ("\r" in (base_url or "")),
                "base_url_preview": (base_url or "")[:120],
            },
            "timestamp": int(_time() * 1000),
        }
        _p.parent.mkdir(parents=True, exist_ok=True)
        with open(_p, "a", encoding="utf-8") as _f:
            _f.write(_json.dumps(_payload, ensure_ascii=False) + "\n")
    except Exception:
        pass
    # #endregion
    if not _TAXIMETER_TEMPLATE.exists():
        return HTMLResponse("404: taximeter template not found", status_code=404)
    html = _TAXIMETER_TEMPLATE.read_text(encoding="utf-8").replace("__WEBAPP_BASE_URL__", base_url)
    return HTMLResponse(html)

@app.get("/track", response_class=HTMLResponse)
@app.get("/tracking", response_class=HTMLResponse)
async def get_user_tracking(order_id: str = "0"):
    """Mijoz uchun haydovchini kuzatish sahifasi."""
    return USER_TRACKING_HTML

@app.get("/taximeter")
async def redirect_taximeter(order_id: str = "0"):
    return RedirectResponse(url=f"/taximeter_v2?order_id={order_id}")


@app.get("/admin", response_class=HTMLResponse)
async def admin_panel(response: Response):
    """Admin Panel - login, dashboard, tariflar, haydovchilar, foydalanuvchilar, loglar."""
    path = Path(__file__).resolve().parent / "templates" / "admin.html"
    if path.exists():
        resp = FileResponse(path)
        resp.headers["Content-Security-Policy"] = (
            "default-src * 'unsafe-inline' 'unsafe-eval' data: blob:; "
            "font-src * data:; "
            "img-src * data:;"
        )
        resp.headers["X-Frame-Options"] = "SAMEORIGIN"
        resp.headers["ngrok-skip-browser-warning"] = "true"
        return resp
    return HTMLResponse("<h1>Admin panel topilmadi</h1>", status_code=404)


# Routerlarni ulash (Xatolar oldi olindi)
app.include_router(webapp.router)
app.include_router(api_router, prefix="/api/v1")

# /api/update_driver_location - qisqa yo'l (Redis-ga yozish)
from app.api.routes.webapp import update_driver_location_api
app.add_api_route("/api/update_driver_location", update_driver_location_api, methods=["POST"])

# ============================================
# FONDA ISHLOVCHI FUNKSIYALAR
# ============================================

async def cleanup_expired_orders():
    """Eskirgan buyurtmalarni har minutda tekshirib turish"""
    # MUHIM: Importni funksiya ichida bajaramiz
    from app.crud.order_crud import OrderCRUD
    
    while True:
        try:
            async with AsyncSessionLocal() as db:
                # Biz klass ichida @staticmethod qilib yaratgan metodni chaqiramiz
                await OrderCRUD.cancel_expired_orders(db)
                # logger.info("🧹 Eskirgan buyurtmalar tozalandi.") # Log juda ko'payib ketmasligi uchun o'chirildi
        except Exception as e:
            logger.error(f"Error in cleanup: {e}")
        
        await asyncio.sleep(60) # Har 60 soniyada bir marta