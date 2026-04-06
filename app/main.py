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
# ============================================
HTML_CONTENT = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="version" content="V25.0">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Timgo Taxi V25.0 - Professional Navigator</title>
    
    <script src="https://telegram.org/js/telegram-web-app.js?v=999"></script>
    <link href="https://cdn.jsdelivr.net/npm/maplibre-gl@3.6.2/dist/maplibre-gl.css" rel="stylesheet"/>
    
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        :root {
            --uber-blue: #276EF1; --uber-dark: #000000; --uber-gray: #1A1A1A;
            --uber-light: #FFFFFF; --uber-success: #05B169; --uber-warning: #FFB800; --uber-danger: #E8504D;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Inter", "Segoe UI", Roboto, sans-serif;
            background: var(--uber-dark); color: var(--uber-light); overflow: hidden; height: 100vh; display: flex; flex-direction: column;
        }
        #map-container { position: relative; flex: 1; overflow: hidden; min-height: 0; }
        #map-wrap {
            position: absolute;
            top: 0; left: 0; right: 0; bottom: 0;
            z-index: 1;
        }
        #map { width: 100%; height: 100%; z-index: 1; padding-bottom: env(safe-area-inset-bottom); box-sizing: border-box; }
        #map.minimized { height: 0vh; opacity: 0; display: none; }
        .bottom-panel {
            position: fixed; bottom: 0; left: 0; width: 100%;
            background: rgba(0,0,0,0.85); backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px);
            padding: 16px 20px; padding-bottom: max(24px, env(safe-area-inset-bottom));
            border-radius: 15px 15px 0 0;
            border-top: 1px solid rgba(255,255,255,0.1); z-index: 1000; margin: 0; box-sizing: border-box;
        }
        .panel-handle { width: 40px; height: 4px; background: rgba(255, 255, 255, 0.2); border-radius: 2px; margin: 0 auto 20px; }
        .distance-info { text-align: center; margin-bottom: 24px; }
        .distance-label { font-size: 14px; color: rgba(255, 255, 255, 0.6); margin-bottom: 8px; text-transform: uppercase; }
        .distance-value { font-size: 42px; font-weight: 800; color: var(--uber-light); line-height: 1; }
        .taximeter-screen { display: none; background: var(--uber-dark); padding: 16px 20px 20px; height: 70vh; overflow-y: auto; }
        .taximeter-screen.active {
            display: block;
            position: fixed;
            inset: 0;
            height: 100%;
            z-index: 1002;
            overflow-y: auto;
        }
        body.taximeter-mode #compassBtn,
        body.taximeter-mode .maplibregl-ctrl-group,
        body.taximeter-mode .maplibregl-ctrl-compass,
        body.taximeter-mode .maplibregl-ctrl-zoom {
            display: none !important;
        }
        .fare-display {
            text-align: center; margin-bottom: 24px; padding: 24px 20px;
            background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%); border-radius: 20px;
        }
        .fare-amount { font-size: 64px; font-weight: 900; color: var(--uber-light); line-height: 1; }
        .stats-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 24px; }
        .stat-card { background: var(--uber-gray); padding: 20px; border-radius: 16px; border: 1px solid rgba(255, 255, 255, 0.1); }
        .action-btn { width: 100%; padding: 18px; border: none; border-radius: 16px; font-size: 16px; font-weight: 700; cursor: pointer; margin-bottom: 12px; }
        .btn-primary { background: var(--uber-blue); color: var(--uber-light); }
        .btn-success { background: var(--uber-success); color: var(--uber-light); }
        .btn-warning { background: var(--uber-warning); color: var(--uber-dark); }
        .btn-danger { background: var(--uber-danger); color: var(--uber-light); }
        .loading-overlay { position: fixed; inset: 0; background: var(--uber-dark); display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 16px; z-index: 9999; }
        .loading-overlay.hidden { opacity: 0; pointer-events: none; }
        .loading-overlay .load-text { font-size: 16px; color: rgba(255,255,255,0.9); }
        .spinner { width: 50px; height: 50px; border: 4px solid rgba(255, 255, 255, 0.1); border-top: 4px solid var(--uber-blue); border-radius: 50%; animation: spin 1s linear infinite; }
        @keyframes spin { to { transform: rotate(360deg); } }
        .driver-marker { width: 40px; height: 40px; background: #dc3545; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 24px; border: 3px solid white; }
        .client-marker { width: 40px; height: 40px; background: #276EF1; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 24px; border: 3px solid white; }
        .leaflet-routing-container, .leaflet-control-attribution { display: none !important; }
        .geo-warn-banner {
            background: rgba(255, 184, 0, 0.95);
            color: #1a1a1a;
            padding: 12px 16px;
            font-size: 14px;
            font-weight: 600;
            text-align: center;
            border-radius: 12px;
            margin-bottom: 12px;
        }
        .sync-status-bar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-wrap: wrap;
            gap: 8px;
            padding: 10px 14px;
            margin: -4px -4px 12px -4px;
            border-radius: 12px;
            font-size: 13px;
            font-weight: 600;
            background: rgba(255, 255, 255, 0.06);
            border: 1px solid rgba(255, 255, 255, 0.12);
        }
        .sync-status-bar .sync-left {
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .sync-dot {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            flex-shrink: 0;
        }
        .sync-dot.online { background: #22c55e; box-shadow: 0 0 8px rgba(34, 197, 94, 0.6); }
        .sync-dot.offline { background: #ef4444; box-shadow: 0 0 8px rgba(239, 68, 68, 0.5); }
        .sync-queue-badge {
            background: rgba(251, 191, 36, 0.2);
            color: #fbbf24;
            padding: 4px 10px;
            border-radius: 999px;
            font-size: 12px;
            border: 1px solid rgba(251, 191, 36, 0.35);
        }
        .sync-queue-badge:empty { display: none; }
        .chat-pulse-banner {
            text-align: center;
            padding: 10px 14px;
            margin: -4px -4px 8px -4px;
            border-radius: 12px;
            font-size: 14px;
            font-weight: 800;
            letter-spacing: 0.04em;
            color: #ecfdf5;
            background: linear-gradient(135deg, rgba(22, 163, 74, 0.4) 0%, rgba(21, 128, 61, 0.55) 100%);
            border: 1px solid rgba(74, 222, 128, 0.5);
            animation: pulse 2s ease-in-out infinite;
        }
        @keyframes pulse {
            0%, 100% {
                opacity: 1;
                box-shadow: 0 0 0 0 rgba(34, 197, 94, 0.55);
            }
            50% {
                opacity: 0.88;
                box-shadow: 0 0 22px 6px rgba(34, 197, 94, 0.4);
            }
        }
        .error-overlay {
            position: fixed;
            inset: 0;
            background: var(--uber-dark);
            color: var(--uber-light);
            display: none;
            align-items: center;
            justify-content: center;
            text-align: center;
            padding: 24px;
            font-size: 16px;
            z-index: 9998;
        }
        .error-overlay.visible { display: flex; flex-direction: column; gap: 16px; }
        .gps-modal {
            position: fixed; inset: 0; background: rgba(0,0,0,0.85);
            display: none; align-items: center; justify-content: center;
            z-index: 10001; padding: 20px;
        }
        .gps-modal.visible { display: flex; }
        .gps-modal-box {
            background: var(--uber-gray);
            border-radius: 20px;
            padding: 28px;
            text-align: center;
            max-width: 340px;
            border: 1px solid rgba(255,255,255,0.15);
        }
        .gps-modal-box h3 { font-size: 18px; margin-bottom: 12px; color: var(--uber-warning); }
        .gps-modal-box p { font-size: 15px; line-height: 1.5; margin-bottom: 20px; opacity: 0.9; }
        .gps-modal-box .btn { padding: 14px 28px; border-radius: 12px; font-weight: 700; cursor: pointer; border: none; background: var(--uber-blue); color: white; }
        .nav-top-bar {
            position: fixed; top: 0; left: 0; right: 0; height: 70px;
            background: #276EF1; color: white; z-index: 1001;
            display: flex; align-items: center; padding: 0 20px; gap: 16px;
            box-shadow: 0 2px 12px rgba(0,0,0,0.2);
        }
        .nav-turn-icon { font-size: 36px; line-height: 1; }
        .nav-info { flex: 1; }
        .nav-meters { font-size: 22px; font-weight: 700; }
        .nav-street { font-size: 14px; opacity: 0.9; }
        .nav-turn-icon svg { width: 40px; height: 40px; }
        .btn-2d3d {
            position: fixed; bottom: 200px; right: 16px; z-index: 999;
            padding: 10px 14px; border-radius: 10px; border: none;
            background: rgba(255,255,255,0.95); color: #333;
            font-weight: 600; font-size: 13px; cursor: pointer;
            box-shadow: 0 2px 10px rgba(0,0,0,0.2);
        }
        #compassBtn {
            position: fixed; bottom: 250px; right: 16px; z-index: 999;
            width: 44px; height: 44px; border-radius: 50%;
            background: white; border: none; cursor: pointer;
            box-shadow: 0 2px 10px rgba(0,0,0,0.2);
            display: flex; align-items: center; justify-content: center;
        }
        #compassBtn svg { width: 24px; height: 24px; fill: #333; }
        .btn-center-map { display: none; }
        /* V16 Professional Navigator - demo UI */
        #top-bar {
            position: fixed; top: 0; left: 0; right: 0; z-index: 1001;
            background: #276EF1; padding: 12px 16px 12px 12px;
            display: flex; align-items: center; gap: 12px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.25); min-height: 62px;
        }
        #turn-icon { flex-shrink: 0; width: 40px; height: 40px; display: flex; align-items: center; justify-content: center; }
        #turn-icon svg { width: 36px; height: 36px; fill: white; }
        #top-dist { font-size: 26px; font-weight: 800; color: white; letter-spacing: -0.5px; min-width: 56px; }
        #top-road { font-size: 16px; font-weight: 500; color: white; opacity: 0.95; flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        #nav-bottom {
            position: fixed; bottom: 0; left: 0; width: 100%; z-index: 1000; margin: 0;
            padding: 12px 14px; padding-bottom: max(24px, env(safe-area-inset-bottom));
            display: flex; align-items: center; justify-content: center;
            background: rgba(0,0,0,0.85); backdrop-filter: blur(16px);
            border-radius: 15px 15px 0 0; box-sizing: border-box;
        }
        #eta-box { background: white; border-radius: 8px; padding: 10px 20px; box-shadow: 0 2px 10px rgba(0,0,0,0.18); text-align: center; min-width: 100px; }
        #eta-t { font-size: 18px; font-weight: 800; color: var(--uber-blue); }
        #eta-d { font-size: 12px; color: #888; margin-top: 2px; }
        .dm-wrap { position: relative; display: inline-block; width: 48px; height: 48px; }
        .dm-ring { position: absolute; inset: -10px; border-radius: 50%; background: rgba(39,110,241,0.15); pointer-events: none; }
        .dm-circle { width: 48px; height: 48px; border-radius: 50%; background: white; box-shadow: 0 3px 14px rgba(0,0,0,0.28); display: flex; align-items: center; justify-content: center; position: relative; }
        .dm-arrow { width: 26px; height: 26px; fill: var(--uber-blue); }
        .dest-wrap { width: 40px; height: 48px; position: relative; }
        .dest-pin { width: 36px; height: 36px; background: var(--uber-danger); border-radius: 50% 50% 50% 0; transform: rotate(-45deg); border: 3px solid white; box-shadow: 0 4px 14px rgba(0,0,0,0.35); display: flex; align-items: center; justify-content: center; margin: 0 auto; }
        .dest-pin span { transform: rotate(45deg); font-size: 9px; color: white; font-weight: 800; text-align: center; line-height: 1; }
    </style>
</head>
<body>
    <div class="gps-modal" id="gpsModal">
        <div class="gps-modal-box">
            <h3>📍 GPS ruxsat kerak</h3>
            <p>GPS ruxsat berilmagan yoki aniqlanmadi. Iltimos telefon sozlamalarida Telegram uchun Location ruxsatini yoqing.</p>
            <button class="btn" onclick="hideGpsModal()">Tushundim</button>
        </div>
    </div>
    <div class="error-overlay" id="errorOverlay"></div>
    <div class="loading-overlay" id="loading"><div class="load-text">Ma&#39;lumotlar yuklanmoqda...</div><div class="spinner"></div></div>
    <div id="top-bar">
        <div id="turn-icon"><svg id="turn-svg" viewBox="0 0 24 24"><path d="M4 12l1.41 1.41L11 7.83V20h2V7.83l5.58 5.59L20 12l-8-8-8 8z"/></svg></div>
        <div id="top-dist">— m</div>
        <div id="top-road">Mijozga yo&#39;l</div>
    </div>
    <div id="map-container"><div id="map-wrap"><div id="map"></div></div></div>
    <button id="compassBtn" title="Shimol / Yo'nalish" style="display:none;"><svg viewBox="0 0 24 24"><path d="M12 2L4 20l8-4 8 4L12 2z"/></svg></button>
    <div id="nav-bottom"><div id="eta-box"><div id="eta-t">--:--</div><div id="eta-d">—</div></div></div>
    <div class="bottom-panel" id="arrivingPanel">
        <div class="panel-handle"></div>
        <div class="distance-info">
            <div style="display:flex;align-items:center;justify-content:center;gap:24px;margin-bottom:16px;">
                <div style="text-align:center;">
                    <div class="distance-label">MASOFA</div>
                    <div class="distance-value">
                        <span id="distanceToClient">0.00</span>
                        <span style="font-size:18px">km</span>
                    </div>
                </div>
                <div style="width:1px;height:48px;background:rgba(255,255,255,0.15);"></div>
                <div style="text-align:center;">
                    <div class="distance-label">VAQT</div>
                    <div class="distance-value" style="font-size:32px;">
                        <span id="timeToClient">—</span>
                        <span style="font-size:16px">min</span>
                    </div>
                </div>
            </div>
        </div>
        <button class="action-btn btn-success" id="arrivedBtn" onclick="handleArrived()">
            ✓ KELDIM — Mijozga xabar berish
        </button>
        <button class="action-btn btn-primary" id="startTripBtn" onclick="handleStartTrip()" style="display:none;">► SAFARNI BOSHLASH</button>
    </div>
    <div class="taximeter-screen" id="taximeterScreen">
        <div class="chat-pulse-banner" id="chatPulseBanner">💬 CHAT: BOTDA</div>
        <div class="sync-status-bar" id="syncStatusBar">
            <div class="sync-left">
                <span class="sync-dot" id="syncConnDot"></span>
                <span id="syncConnText">—</span>
            </div>
            <span class="sync-queue-badge" id="syncQueueBadge"></span>
        </div>
        <div class="fare-display">
            <div style="font-size: 14px; opacity: 0.7;">Joriy to&#39;lov</div>
            <div class="fare-amount" id="currentFare">0</div>
            <div style="font-weight: 600;">SO&#39;M</div>
        </div>
        <div class="stats-grid">
            <div class="stat-card"><div>📏 Masofa</div><div class="stat-value"><span id="tripDistance">0.0</span> km</div></div>
            <div class="stat-card"><div>⏱️ Vaqt</div><div class="stat-value" id="tripTime">00:00</div></div>
        </div>
        <button class="action-btn btn-warning" id="waitingBtn" onclick="toggleWaiting()">⏸ PAUZA / KUTISH</button>
        <button class="action-btn btn-danger" id="finishBtn" onclick="handleFinish()">◼ SAFARNI YAKUNLASH</button>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/maplibre-gl@3.6.2/dist/maplibre-gl.js"></script>
    <script src="https://unpkg.com/@turf/turf@6/turf.min.js?v=8.0.0"></script>
    <script>
        (function(){
            var tg = (window.Telegram && window.Telegram.WebApp) ? window.Telegram.WebApp : null;
            if (tg) {
                try { tg.ready(); tg.expand(); } catch (_) {}
            }
            if (location.protocol !== 'https:' && location.hostname !== 'localhost' && location.hostname.indexOf('127.') !== 0) {
                document.body.innerHTML = '<div style="padding:24px;text-align:center;font-size:16px;">Geolocation faqat HTTPS da ishlaydi. Iltimos, xavfsiz manzil orqali oching.</div>';
                throw new Error('HTTPS required');
            }
        })();
        let TARIFF = { startPrice: 5000, pricePerKm: 2500, pricePerMinWaiting: 500, minDistanceUpdate: 0.02 };
        let ORDER_DATA = null;
        const tg = (window.Telegram && window.Telegram.WebApp) ? window.Telegram.WebApp : { expand: function(){}, ready: function(){} };

        let map, tileLayer, driverMarker, clientMarker, destMarker, routeControl, routeControlAB;
        let routeRoadDistanceKm = null;
        let routeInstructions = [], routeCoordinates = [], routePolyline = null, routeDecorator = null;
        // Turf route line feature (haydovchi uchun snapping va progressive trim)
        let _driverRouteLine = null;       // turf.lineString — [lon,lat] koordinatlarda
        let _driverRouteCoords = [];       // [[lon,lat], ...] — OSRM raw coords (GeoJSON tartib)
        let map2dMode = true;
        let arrowEl = null;
        let tLat = null, tLng = null, dLat = null, dLng = null, brg = 0, spd = 0;
        let pLat = null, pLng = null, locked = true, lastCam = 0;
        let simIdx = 0, simOn = false, simTmr = null, turnI = 0, distKm = 1;
        let displayBearing = 0, targetBearing = 0;
        let displayHeading = 0;
        let _camBlockUntil = 0;
        let _lastCamLat = null, _lastCamLng = null, _lastCamBrg = 0, _lastCamZoom = 0;
        let _velLat = 0, _velLng = 0;
        let _smoothVelLat = 0, _smoothVelLng = 0;
        let _gpsAnchorLat = null, _gpsAnchorLng = null, _gpsAnchorMs = 0;
        let _predLat = null, _predLng = null;
        let _camLat = null, _camLng = null;
        let _routeAnchorIdx = 0;
        let _pendingGps = null;    // queued GPS update received before _driverRouteLine was ready
        let _firstSnapDone = false; // true after the first successful Turf snap; guards dead zone
        let _snapRouteLine = null;  // trimmed forward-only snap line; rebuilt after each snap
        let _lastRerouteMs = 0;    // timestamp of last reroute request (5 s cooldown)
        let northUpMode = false;
        let isManualMode = false, gestureStartAngle = null, gestureStartBearing = 0, manualBearing = 0, manualModeTimer = null, useManualBearing = false;
        let renderLoopRunning = false;
        const TSVG = {
            right: '<path d="M6 6v2h8.59L5 17.59 6.41 19 16 9.41V18h2V6z"/>',
            left: '<path d="M18 6v2H9.41L19 17.59 17.59 19 8 9.41V18H6V6z"/>',
            straight: '<path d="M4 12l1.41 1.41L11 7.83V20h2V7.83l5.58 5.59L20 12l-8-8-8 8z"/>',
            arrive: '<path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z"/>'
        };
        let appState = 'arriving';
        let tripData = { distance: 0, waitingTime: 0, elapsedSeconds: 0, isWaiting: false, lastPosition: null };
        let intervals = { timer: null, position: null };

        const API_BASE_URL = '__WEBAPP_BASE_URL__';
        fetch(API_BASE_URL + '/api/webapp/tariff?v=' + Date.now(), { headers: { 'ngrok-skip-browser-warning': '1' } })
            .then(function(r){ return r.json(); })
            .then(function(d){ TARIFF.startPrice = d.startPrice||5000; TARIFF.pricePerKm = d.pricePerKm||2500; TARIFF.pricePerMinWaiting = d.pricePerMinWaiting||500; TARIFF.minDistanceUpdate = d.minDistanceUpdate||0.02; })
            .catch(function(){});
        const urlParams = new URLSearchParams(window.location.search);
        const ORDER_ID_CURRENT = urlParams.get('order_id');
        const WEBAPP_TOKEN = urlParams.get('token');
        function webappHeaders() {
            var h = { 'ngrok-skip-browser-warning': 'true', 'Content-Type': 'application/json' };
            if (WEBAPP_TOKEN) h['X-WebApp-Token'] = WEBAPP_TOKEN;
            return h;
        }
        if (ORDER_ID_CURRENT) console.log("Joriy buyurtma ID:", ORDER_ID_CURRENT);
        const MAX_DISTANCE_KM = 500;

        var PENDING_TRIPS_KEY = 'pending_trips';
        var pendingFlushLock = false;

        function getPendingTrips() {
            try {
                var raw = localStorage.getItem(PENDING_TRIPS_KEY);
                if (!raw) return [];
                var arr = JSON.parse(raw);
                return Array.isArray(arr) ? arr : [];
            } catch (e) { return []; }
        }
        function setPendingTrips(arr) {
            try {
                localStorage.setItem(PENDING_TRIPS_KEY, JSON.stringify(arr));
            } catch (e) {}
        }
        function enqueuePendingTrip(item) {
            item.id = item.id || ('t_' + Date.now() + '_' + Math.random().toString(36).slice(2, 11));
            item.createdAt = item.createdAt || Date.now();
            var q = getPendingTrips();
            q.push(item);
            setPendingTrips(q);
            return item.id;
        }
        function updateSyncUI() {
            var online = typeof navigator !== 'undefined' && navigator.onLine;
            var dot = document.getElementById('syncConnDot');
            var txt = document.getElementById('syncConnText');
            var badge = document.getElementById('syncQueueBadge');
            if (dot) {
                dot.className = 'sync-dot ' + (online ? 'online' : 'offline');
            }
            if (txt) {
                txt.textContent = online ? 'Online' : 'Offline';
            }
            var n = getPendingTrips().length;
            if (badge) {
                badge.textContent = n > 0 ? ('Navbat: ' + n) : '';
            }
        }
        function sendPendingItem(item) {
            var params = new URLSearchParams({ new_status: 'completed' });
            params.set('final_price', String(item.final_price));
            if (item.distance_km != null && !isNaN(Number(item.distance_km))) {
                params.set('distance_km', String(item.distance_km));
            }
            var statusUrl = item.apiBaseUrl + '/api/webapp/order/' + item.orderId + '/status?' + params.toString() + '&v=' + Date.now();
            if (item.token) statusUrl += '&token=' + encodeURIComponent(item.token);
            var headers = { 'ngrok-skip-browser-warning': 'true', 'Content-Type': 'application/json' };
            if (item.token) headers['X-WebApp-Token'] = item.token;
            return fetch(statusUrl, { method: 'POST', headers: headers });
        }
        function handleTripSyncSuccess(item) {
            if (String(item.orderId) !== String(ORDER_ID_CURRENT)) return;
            if (!window._orderCompleteUiDone) window._orderCompleteUiDone = {};
            if (window._orderCompleteUiDone[item.orderId]) return;
            window._orderCompleteUiDone[item.orderId] = true;
            try {
                clearInterval(intervals.timer);
            } catch (e) {}
            if (ORDER_DATA) ORDER_DATA.status = 'completed';
            var loadingEl = document.getElementById('loading');
            if (loadingEl) loadingEl.classList.add('hidden');
            var finalFareStr = String(item.final_price);
            var payload = {
                status: 'finished',
                order_id: parseInt(item.orderId, 10),
                final_price: parseFloat(item.final_price) || 0,
                distance_km: item.distance_km != null ? item.distance_km : 0
            };
            if (tg && tg.showAlert) {
                tg.showAlert('Safar yakunlandi! Tolov: ' + finalFareStr + ' som', function() {
                    if (tg && tg.sendData) tg.sendData(JSON.stringify(payload));
                    if (tg && tg.close) tg.close();
                });
            } else {
                if (tg && tg.sendData) tg.sendData(JSON.stringify(payload));
                if (tg && tg.close) tg.close();
            }
        }
        async function flushPendingTrips() {
            if (pendingFlushLock) return;
            pendingFlushLock = true;
            try {
                var q = getPendingTrips();
                var remaining = [];
                for (var i = 0; i < q.length; i++) {
                    var item = q[i];
                    try {
                        var res = await sendPendingItem(item);
                        if (res.ok) {
                            handleTripSyncSuccess(item);
                        } else {
                            var st = res.status;
                            if (st === 400 || st === 404 || st === 422) {
                                /* mijoz xato — qayta yuborish foydasiz */
                            } else {
                                remaining.push(item);
                            }
                        }
                    } catch (e) {
                        remaining.push(item);
                    }
                }
                setPendingTrips(remaining);
                updateSyncUI();
            } finally {
                pendingFlushLock = false;
            }
        }

        let CLIENT_LOCATION = null;
        let lastDriverLocation = null;
        let lastHeading = 0;
        let lastSentLocation = null;
        let lastSentTime = 0;
        const MIN_DISTANCE_M = 15;
        const THROTTLE_MS = 7000;
        let gpsErrorShown = false;
        let navAutoMode = true;
        let returnToNavTimer = null;
        let _navProgrammatic = false;
        let _bearingAnimId = null;
        let lastPositionTime = null;
        let lastGpsSpeedKmh = null;
        let _markerAnimId = null;
        const CAMERA_OFFSET_M = 150;

        function haversineM(lat1, lon1, lat2, lon2) {
            var R = 6371000;
            var dLat = (lat2 - lat1) * Math.PI / 180;
            var dLon = (lon2 - lon1) * Math.PI / 180;
            var a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
                Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
                Math.sin(dLon / 2) * Math.sin(dLon / 2);
            return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
        }

        function lerp(a, b, t) { return a + (b - a) * t; }
        function lerpAngle(a, b, t) {
            var diff = ((b - a + 540) % 360) - 180;
            return (a + diff * t + 360) % 360;
        }
        function circularMeanHeadings(arr) {
            if (!arr || arr.length === 0) return 0;
            var sinSum = 0, cosSum = 0;
            arr.forEach(function(h) {
                sinSum += Math.sin(h * Math.PI / 180);
                cosSum += Math.cos(h * Math.PI / 180);
            });
            var smooth = Math.atan2(sinSum, cosSum) * 180 / Math.PI;
            return smooth < 0 ? smooth + 360 : smooth;
        }
        function speedToZoom(s) { return s > 70 ? 15 : s > 40 ? 15.5 : s > 20 ? 16.5 : 17.5; }
        function getZoomBySpeed(speedKmh) { return speedToZoom(speedKmh); }
        // Marshrutning snapped nuqtasidagi yo'nalishini hisoblaydi (GPS heading yo'q yoki ishonchsiz bo'lganda)
        function getRouteTangentBearing(snappedLon, snappedLat) {
            if (!_driverRouteLine || !_driverRouteCoords || _driverRouteCoords.length < 2) return null;
            try {
                var pt = turf.point([snappedLon, snappedLat]);
                var snapped = turf.nearestPointOnLine(_driverRouteLine, pt, { units: 'kilometers' });
                var idx = snapped && snapped.properties ? (snapped.properties.index || 0) : 0;
                idx = Math.min(idx, _driverRouteCoords.length - 2);
                var p1 = _driverRouteCoords[idx];
                var p2 = _driverRouteCoords[idx + 1];
                if (p1 && p2) return calcBearing(p1[1], p1[0], p2[1], p2[0]);
            } catch (_) {}
            return null;
        }
        // Route-based dead reckoning: walks distM meters along _driverRouteCoords starting
        // from (ancLat, ancLng) which lies within segment startIdx.
        // Stays on road geometry through curves — superior to linear extrapolation.
        // O(k) where k = segments crossed (typically 1-3 for a 2s prediction window).
        function advanceAlongRoute(ancLat, ancLng, startIdx, distM) {
            if (!_driverRouteCoords || _driverRouteCoords.length < 2 || distM <= 0) return null;
            var idx = Math.max(0, Math.min(startIdx, _driverRouteCoords.length - 2));
            var rem = distM;
            // First: walk from anchor to the end of its segment.
            var c1End = _driverRouteCoords[idx + 1];
            var distToSegEnd = haversineM(ancLat, ancLng, c1End[1], c1End[0]);
            if (rem <= distToSegEnd) {
                var f = distToSegEnd > 0 ? rem / distToSegEnd : 0;
                return [ancLat + (c1End[1] - ancLat) * f, ancLng + (c1End[0] - ancLng) * f];
            }
            rem -= distToSegEnd;
            // Then walk full segments until rem is exhausted.
            for (var i = idx + 1; i < _driverRouteCoords.length - 1; i++) {
                var cp1 = _driverRouteCoords[i], cp2 = _driverRouteCoords[i + 1];
                var seg = haversineM(cp1[1], cp1[0], cp2[1], cp2[0]);
                if (rem <= seg) {
                    var f = seg > 0 ? rem / seg : 0;
                    return [cp1[1] + (cp2[1] - cp1[1]) * f, cp1[0] + (cp2[0] - cp1[0]) * f];
                }
                rem -= seg;
            }
            var last = _driverRouteCoords[_driverRouteCoords.length - 1];
            return [last[1], last[0]];
        }
        // Returns [snappedLat, snappedLng, segmentIdx].
        // Uses cos(lat) to convert longitude degrees into the same metric scale as latitude
        // degrees before computing the projection dot product.
        // Without this correction, 1° lon ≈ 84 km at lat 41° vs 1° lat ≈ 111 km → 24%
        // projection error → marker consistently offset from road.
        function snapToRoute(lat, lng) {
            var coords = routeCoordinates;
            if (!coords || coords.length < 2) return [lat, lng, 0];
            var toLL = function(c) { return c && (c.lat != null) ? [c.lat, c.lng] : [c[0], c[1]]; };
            var cosLat = Math.cos(lat * Math.PI / 180);
            var best = null, bestIdx = 0, bd = Infinity;
            for (var i = 0; i < coords.length - 1; i++) {
                var p1 = toLL(coords[i]), p2 = toLL(coords[i + 1]);
                var y1 = p1[0], x1 = p1[1], y2 = p2[0], x2 = p2[1];
                // Scale longitude deltas by cosLat so the dot product is proportional to meters.
                var dy = y2 - y1;
                var dx = (x2 - x1) * cosLat;
                var l2 = dy * dy + dx * dx;
                if (!l2) continue;
                var t = Math.max(0, Math.min(1, ((lat - y1) * dy + (lng - x1) * cosLat * dx) / l2));
                var py = y1 + t * (y2 - y1);
                var px = x1 + t * (x2 - x1);
                var d = haversineM(lat, lng, py, px); // metric distance — correct basis for comparison
                if (d < bd) { bd = d; best = [py, px]; bestIdx = i; }
            }
            if (best && bd < 500) return [best[0], best[1], bestIdx];
            return [lat, lng, 0];
        }
        function getOffsetCenter(lat, lon, bearingDeg, meters) {
            if (bearingDeg == null || isNaN(bearingDeg)) return [lat, lon];
            var R = 6378137;
            var d = meters / R;
            var br = bearingDeg * Math.PI / 180;
            var lat1 = lat * Math.PI / 180;
            var lon1 = lon * Math.PI / 180;
            var lat2 = Math.asin(Math.sin(lat1) * Math.cos(d) + Math.cos(lat1) * Math.sin(d) * Math.cos(br));
            var lon2 = lon1 + Math.atan2(Math.sin(br) * Math.sin(d) * Math.cos(lat1), Math.cos(d) - Math.sin(lat1) * Math.sin(lat2));
            return [lat2 * 180 / Math.PI, lon2 * 180 / Math.PI];
        }
        function addDriverMarker(lat, lon) {
            if (driverMarker) return;
            var wrap = document.createElement('div');
            wrap.className = 'dm-wrap';
            var circle = document.createElement('div');
            circle.className = 'dm-circle';
            var svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
            svg.setAttribute('viewBox', '0 0 24 24');
            svg.setAttribute('class', 'dm-arrow');
            svg.innerHTML = '<path d="M12 2L4.5 20.29l.71.71L12 18l6.79 3 .71-.71z"/>';
            arrowEl = svg;
            circle.appendChild(svg);
            wrap.appendChild(circle);
            driverMarker = new maplibregl.Marker({
                element: wrap,
                anchor: 'center',
                rotationAlignment: 'viewport', // viewport: MapLibre elementga o'z rotation qo'shmaydi — CSS bilan to'liq nazorat
                pitchAlignment: 'viewport'
            }).setLngLat([lon, lat]).addTo(map);
        }
        function followCam() {
            if (!locked || !map || dLat == null || dLng == null) return;
            var zoom = speedToZoom(spd);
            var pitch = 60;
            var mpp = 156543 * Math.cos(dLat * Math.PI / 180) / Math.pow(2, zoom);
            var fwd = window.innerHeight * 0.15 * mpp / Math.cos(pitch * Math.PI / 180);
            var cc = getOffsetCenter(dLat, dLng, displayBearing, fwd);
            map.easeTo({
                center: [cc[1], cc[0]],
                bearing: displayBearing,
                pitch: pitch,
                zoom: zoom,
                duration: 500,
                easing: function(x) { return x < 0.5 ? 2*x*x : 1 - Math.pow(-2*x+2,2)/2; }
            });
        }
        function recenter() {
            locked = true;
            _camBlockUntil = Date.now() + 380;
            if (dLat != null && dLng != null && map) {
                var zoom = speedToZoom(spd);
                var pitch = 60;
                var mpp = 156543 * Math.cos(dLat * Math.PI / 180) / Math.pow(2, zoom);
                var fwd = window.innerHeight * 0.15 * mpp / Math.cos(pitch * Math.PI / 180);
                var cc = getOffsetCenter(dLat, dLng, displayBearing, fwd);
                map.easeTo({
                    center: [cc[1], cc[0]],
                    bearing: displayBearing,
                    pitch: pitch,
                    zoom: zoom,
                    duration: 350,
                    easing: function(x) { return x < 0.5 ? 2*x*x : 1 - Math.pow(-2*x+2,2)/2; }
                });
            } else if (lastDriverLocation && map) {
                map.easeTo({
                    center: [lastDriverLocation.lon, lastDriverLocation.lat],
                    zoom: map.getZoom() || 17,
                    bearing: displayBearing,
                    pitch: 60,
                    duration: 350
                });
            }
        }
        function zoomIn() { if (map) map.zoomIn(); }
        function zoomOut() { if (map) map.zoomOut(); }
        function renderLoop() {
            requestAnimationFrame(function(t) {
                var lt = renderLoop.lt;
                var dt = lt ? Math.min((t - lt) / 1000, 0.1) : 0.016;
                renderLoop.lt = t;

                var _nowMs = Date.now();

                // predictPosition ─────────────────────────────────────────────────────────
                // _drScale: smoothly activates dead reckoning between 2–5 km/h.
                // Eliminates the flicker that a hard spd>2 threshold causes at low speed.
                // Formula: 0 when spd≤2, ramps linearly to 1 at spd=5, capped at 1.
                var _drScale = Math.min(Math.max((spd - 2) / 3, 0), 1);
                if (_gpsAnchorLat !== null && _drScale > 0) {
                    var _drSec = Math.min((_nowMs - _gpsAnchorMs) / 1000, 2.5);
                    var _drDist = (spd / 3.6) * _drSec * _drScale; // meters to extrapolate
                    // Route-based prediction: follows road geometry through curves.
                    // Falls back to spherical-bearing projection if no route loaded.
                    var _rp = advanceAlongRoute(_gpsAnchorLat, _gpsAnchorLng, _routeAnchorIdx, _drDist);
                    if (_rp !== null) {
                        _predLat = _rp[0];
                        _predLng = _rp[1];
                    } else {
                        // Spherical projection along displayBearing — correct for short arcs.
                        var _R = 6371000;
                        var _bRad = displayBearing * Math.PI / 180;
                        var _lat1R = _gpsAnchorLat * Math.PI / 180;
                        var _dR = _drDist / _R;
                        var _lat2R = Math.asin(Math.sin(_lat1R) * Math.cos(_dR) + Math.cos(_lat1R) * Math.sin(_dR) * Math.cos(_bRad));
                        _predLat = _lat2R * 180 / Math.PI;
                        _predLng = _gpsAnchorLng + Math.atan2(Math.sin(_bRad) * Math.sin(_dR) * Math.cos(_lat1R), Math.cos(_dR) - Math.sin(_lat1R) * Math.sin(_lat2R)) * 180 / Math.PI;
                    }
                } else {
                    _predLat = tLat;
                    _predLng = tLng;
                }
                // Snap predicted position back onto the route every frame.
                // Eliminates off-road drift from the spherical fallback and straight-line
                // lerp gaps at corners — prediction now always sits exactly on the polyline.
                if (typeof turf !== 'undefined' && _driverRouteLine && _driverRouteLine.geometry && _predLat !== null) {
                    try {
                        var _predSnap = turf.nearestPointOnLine(_driverRouteLine, turf.point([_predLng, _predLat]));
                        if (_predSnap && _predSnap.geometry && _predSnap.geometry.coordinates) {
                            _predLat = _predSnap.geometry.coordinates[1];
                            _predLng = _predSnap.geometry.coordinates[0];
                        }
                    } catch (_) {}
                }

                // updatePosition ─────────────────────────────────────────────────────────
                // τ_pos = 0.50s when parked: heavily damps GPS noise, prevents jitter.
                // τ_pos = 0.12s when moving: fast settling (~360ms), GPS jumps absorbed.
                // α = 1 - exp(-dt / τ)
                var _tauPos = spd < 3 ? 0.50 : 0.12;
                if (_predLat !== null && _predLng !== null) {
                    if (dLat === null) { dLat = _predLat; dLng = _predLng; }
                    else {
                        var _posDecay = Math.exp(-dt / _tauPos);
                        dLat = _predLat + (dLat - _predLat) * _posDecay;
                        dLng = _predLng + (dLng - _predLng) * _posDecay;
                        // Snap to exact target once sub-nanodegree to stop floating-point jitter.
                        if (Math.abs(dLat - _predLat) < 1e-9 && Math.abs(dLng - _predLng) < 1e-9) {
                            dLat = _predLat; dLng = _predLng;
                        }
                    }
                }

                // Camera position smoothing ───────────────────────────────────────────────
                // τ_cam = 0.04s: eliminates any remaining float noise in dLat/dLng before
                // it reaches the GPU. Adds <60ms imperceptible lag at 60fps.
                if (dLat !== null) {
                    if (_camLat === null) { _camLat = tLat !== null ? tLat : dLat; _camLng = tLng !== null ? tLng : dLng; }
                    else {
                        var _camDecay = Math.exp(-dt / 0.04);
                        _camLat = dLat + (_camLat - dLat) * _camDecay;
                        _camLng = dLng + (_camLng - dLng) * _camDecay;
                    }
                }

                // updateBearing ─────────────────────────────────────────────────────────
                // τ_brg = 0.80 - 0.65 × min(spd/30, 1)
                // τ at  0 km/h: 0.80s — absorbs GPS bearing noise when nearly stopped.
                // τ at 30 km/h: 0.15s — tracks highway bends without lag.
                // τ at 60 km/h: 0.15s — capped; faster would overshoot sharp turns.
                if (!useManualBearing) targetBearing = northUpMode ? 0 : brg;
                var _tauBrg = 0.80 - 0.65 * Math.min(spd / 30, 1);
                var _brgDecay = Math.exp(-dt / _tauBrg);
                var _brgShortcut = ((targetBearing - displayBearing + 540) % 360) - 180;
                displayBearing = (displayBearing + _brgShortcut * (1 - _brgDecay) + 360) % 360;

                // Arrow heading: τ = 0.08s — leads the camera turn so arrow "points ahead".
                var _headDecay = Math.exp(-dt / 0.08);
                var _hdShortcut = ((brg - displayHeading + 540) % 360) - 180;
                displayHeading = (displayHeading + _hdShortcut * (1 - _headDecay) + 360) % 360;
                if (arrowEl) arrowEl.style.transform = 'rotate(' + ((displayHeading - displayBearing + 720) % 360) + 'deg)';

                if (driverMarker && dLat !== null && dLng !== null) {
                    driverMarker.setLngLat([dLng, dLat]);
                }

                // updateCamera ──────────────────────────────────────────────────────────
                // Uses _camLat/Lng (camera-smoothed position) — not raw dLat/dLng —
                // to avoid float jitter reaching the GPU.
                // _screenRatio: 0.15 at rest → 0.25 at 80 km/h.
                // Larger ratio = vehicle lower on screen = more road visible ahead.
                // GPU redraw suppressed when position and bearing are sub-pixel stable.
                if (_camLat !== null) {
                    var _zoom = speedToZoom(spd);
                    var _brgDelta = Math.abs(((displayBearing - _lastCamBrg + 540) % 360) - 180);
                    var _moved = Math.abs(_camLat - _lastCamLat) > 1e-6 || Math.abs(_camLng - _lastCamLng) > 1e-6;
                    if (_moved || _brgDelta > 0.05 || _zoom !== _lastCamZoom) {
                        map.jumpTo({ center: [_camLng, _camLat], bearing: displayBearing, pitch: 60, zoom: _zoom });
                        _lastCamLat = _camLat;
                        _lastCamLng = _camLng;
                        _lastCamBrg = displayBearing;
                        _lastCamZoom = _zoom;
                    }
                }

                renderLoop();
            });
        }
        function updateNavUI() {
            var distM = distKm >= 1 ? (distKm.toFixed(1) + 'km') : (Math.round(distKm * 1000) + 'm');
            var inst = routeInstructions[turnI] || routeInstructions[0];
            var street = inst && inst.text ? inst.text : "Mijozga yol";
            var turnType = inst && inst.type != null ? inst.type : -1;
            var tkey = (turnType >= 2 && turnType <= 4) ? 'right' : (turnType >= 6 && turnType <= 8) ? 'left' : (turnType === 0) ? 'straight' : 'straight';
            if (routeInstructions.length && (turnI >= routeInstructions.length - 1)) tkey = 'arrive';
            var svg = document.getElementById('turn-svg');
            if (svg) svg.innerHTML = TSVG[tkey] || TSVG.straight;
            var topDist = document.getElementById('top-dist');
            var topRoad = document.getElementById('top-road');
            if (topDist) topDist.textContent = distM;
            if (topRoad) topRoad.textContent = street;
            var avg = Math.max(spd, 8);
            var mins = Math.round((distKm / avg) * 60);
            var eta = new Date();
            eta.setMinutes(eta.getMinutes() + mins);
            var et = document.getElementById('eta-t');
            var ed = document.getElementById('eta-d');
            if (et) et.textContent = eta.getHours().toString().padStart(2,'0') + ':' + eta.getMinutes().toString().padStart(2,'0');
            if (ed) ed.textContent = distKm >= 1 ? (distKm.toFixed(1) + 'km') : (Math.round(distKm * 1000) + 'm');
        }
        function calcBearing(lat1, lon1, lat2, lon2) {
            var dLon = (lon2 - lon1) * Math.PI / 180;
            var lat1r = lat1 * Math.PI / 180, lat2r = lat2 * Math.PI / 180;
            var y = Math.sin(dLon) * Math.cos(lat2r);
            var x = Math.cos(lat1r) * Math.sin(lat2r) - Math.sin(lat1r) * Math.cos(lat2r) * Math.cos(dLon);
            return (Math.atan2(y, x) * 180 / Math.PI + 360) % 360;
        }

        function showGpsModal() {
            var m = document.getElementById('gpsModal');
            if (m) m.classList.add('visible');
        }
        function hideGpsModal() {
            var m = document.getElementById('gpsModal');
            if (m) m.classList.remove('visible');
        }

        function isValidCoord(lat, lon) {
            return lat != null && lon != null && !isNaN(lat) && !isNaN(lon) && lat >= -90 && lat <= 90 && lon >= -180 && lon <= 180;
        }

        function showError(msg) {
            var el = document.getElementById('errorOverlay');
            if (el) {
                el.textContent = msg;
                el.classList.add('visible');
            }
            document.getElementById('loading').classList.add('hidden');
        }

        async function fetchClientLocation() {
            const orderId = ORDER_ID_CURRENT;
            if (!orderId) {
                showError("Order ID " + "topilmadi.");
                return;
            }
            try {
                var q = '?v=' + Date.now(); if (WEBAPP_TOKEN) q += '&token=' + encodeURIComponent(WEBAPP_TOKEN);
                const response = await fetch(API_BASE_URL + '/api/webapp/order/' + orderId + q, {
                    headers: webappHeaders()
                });
                if (!response.ok) {
                    var errText = "Order topilmadi";
                    try {
                        var j = await response.json();
                        if (j && j.detail) errText = j.detail;
                    } catch (_) {}
                    showError(errText);
                    return;
                }
                const data = await response.json();
                var lat = data.pickup_latitude, lon = data.pickup_longitude;
                if (!isValidCoord(lat, lon)) {
                    showError("Mijoz joylashuvi noto'g'ri.");
                    return;
                }
                CLIENT_LOCATION = { lat: lat, lon: lon };
                ORDER_DATA = data;
                ORDER_DATA.pickup_latitude = lat;
                ORDER_DATA.pickup_longitude = lon;
                ORDER_DATA.status = data.status || 'accepted';
            } catch (error) {
                showError("Serverga ulanishda xatolik.");
            }
        }

        const AVG_SPEED_KMH = 40;

        function showOrderCompleted(status) {
            document.getElementById('loading').classList.add('hidden');

            var isCompleted = (status === 'completed');
            var icon = isCompleted ? '✅' : '❌';
            var title = isCompleted ? 'Safar yakunlangan' : 'Buyurtma bekor qilingan';

            var overlay = document.createElement('div');
            overlay.style.cssText = [
                'position:fixed',
                'inset:0',
                'background:#000000',
                'color:#ffffff',
                'display:flex',
                'flex-direction:column',
                'align-items:center',
                'justify-content:center',
                'text-align:center',
                'padding:32px',
                'gap:20px',
                'z-index:99999'
            ].join(';');

            var iconEl = document.createElement('div');
            iconEl.style.fontSize = '64px';
            iconEl.textContent = icon;

            var titleEl = document.createElement('div');
            titleEl.style.cssText = 'font-size:24px;font-weight:700;';
            titleEl.textContent = title;

            var subEl = document.createElement('div');
            subEl.style.cssText = 'font-size:15px;color:rgba(255,255,255,0.6);';
            subEl.textContent = "Bu buyurtma allaqachon yakunlangan.";

            var btn = document.createElement('button');
            btn.style.cssText = [
                'margin-top:16px',
                'padding:16px 32px',
                'background:#276EF1',
                'color:#ffffff',
                'border:none',
                'border-radius:16px',
                'font-size:16px',
                'font-weight:700',
                'cursor:pointer'
            ].join(';');
            btn.textContent = 'Yopish';
            btn.onclick = function() {
                var tgApp = window.Telegram && window.Telegram.WebApp;
                if (tgApp && tgApp.close) tgApp.close();
            };

            overlay.appendChild(iconEl);
            overlay.appendChild(titleEl);
            overlay.appendChild(subEl);
            overlay.appendChild(btn);
            document.body.appendChild(overlay);
        }

        async function init() {
            await fetchClientLocation();
            if (!ORDER_DATA) return;

            /* Order already completed or cancelled */
            if (ORDER_DATA.status === 'completed' || ORDER_DATA.status === 'cancelled') {
                showOrderCompleted(ORDER_DATA.status);
                return;
            }

            /* Trip already started */
            if (ORDER_DATA.status === 'in_progress') {
                appState = 'trip';
            }

            initMap();
            startDriverTracking();
            updateSyncUI();
            flushPendingTrips();
        }

        function initMap() {
            if (!ORDER_DATA || !isValidCoord(ORDER_DATA.pickup_latitude, ORDER_DATA.pickup_longitude)) return;
            var lat = ORDER_DATA.pickup_latitude;
            var lon = ORDER_DATA.pickup_longitude;

            var driverLat = lat;
            var driverLng = lon;

            map = new maplibregl.Map({
                container: 'map',
                style: {
                    version: 8,
                    sources: {
                        osm: {
                            type: 'raster',
                            tiles: [
                                'https://a.tile.openstreetmap.org/{z}/{x}/{y}.png',
                                'https://b.tile.openstreetmap.org/{z}/{x}/{y}.png',
                                'https://c.tile.openstreetmap.org/{z}/{x}/{y}.png'
                            ],
                            tileSize: 256,
                            maxzoom: 19
                        }
                    },
                    layers: [{
                        id: 'osm-tiles',
                        type: 'raster',
                        source: 'osm'
                    }]
                },
                center: [driverLng, driverLat],
                zoom: 17,
                pitch: 55,
                bearing: 0,
                antialias: true
            });

            map.on('dragstart', function() { locked = false; });
            map.on('load', function() {
                try {
                    var dp = document.createElement('div');
                    dp.className = 'dest-wrap';
                    dp.innerHTML = '<div class="dest-pin"><span id="destPinLabel">MANZIL</span></div>';
                    clientMarker = new maplibregl.Marker({
                        element: dp,
                        anchor: 'bottom'
                    }).setLngLat([lon, lat]).addTo(map);
                    setInterval(refreshDistanceDisplay, 5000);
                    var destLat = ORDER_DATA.destination_latitude;
                    var destLon = ORDER_DATA.destination_longitude;
                    if (destLat != null && destLon != null && isValidCoord(destLat, destLon) && (Math.abs(destLat - lat) > 0.0001 || Math.abs(destLon - lon) > 0.0001)) {
                        var dw = document.createElement('div');
                        dw.className = 'dest-wrap';
                        dw.innerHTML = '<div class="dest-pin"><span>B</span></div>';
                        destMarker = new maplibregl.Marker({
                            element: dw,
                            anchor: 'bottom'
                        }).setLngLat([destLon, destLat]).addTo(map);
                        drawRouteAB({ lat: lat, lng: lon }, { lat: destLat, lng: destLon });
                    }
                    document.getElementById('loading').classList.add('hidden');
                    if (!renderLoopRunning) { renderLoopRunning = true; renderLoop(); }
                    setupMapGestures();
                } catch (e) {}
            });
        }

        function getAngleFromTouches(touches) {
            var dx = touches[1].clientX - touches[0].clientX;
            var dy = touches[1].clientY - touches[0].clientY;
            return Math.atan2(dy, dx) * 180 / Math.PI;
        }
        function setupMapGestures() {
            var mapWrap = document.getElementById('map-wrap');
            var compassBtn = document.getElementById('compassBtn');
            if (compassBtn) {
                compassBtn.style.display = 'flex';
                compassBtn.addEventListener('click', function() {
                    northUpMode = !northUpMode;
                    locked = !northUpMode;
                    if (northUpMode) {
                        targetBearing = 0;
                        compassBtn.style.background = '#1A73E8';
                        if (compassBtn.querySelector('svg')) compassBtn.querySelector('svg').style.filter = 'invert(1)';
                    } else {
                        locked = true;
                        compassBtn.style.background = 'white';
                        if (compassBtn.querySelector('svg')) compassBtn.querySelector('svg').style.filter = 'none';
                    }
                });
            }
            if (mapWrap) {
                mapWrap.addEventListener('touchstart', function(e) {
                    if (e.touches.length === 2) {
                        isManualMode = true;
                        useManualBearing = true;
                        locked = false;
                        gestureStartAngle = getAngleFromTouches(e.touches);
                        gestureStartBearing = displayBearing;
                        clearTimeout(manualModeTimer);
                    }
                });
                mapWrap.addEventListener('touchmove', function(e) {
                    if (e.touches.length === 2 && isManualMode) {
                        e.preventDefault();
                        var currentAngle = getAngleFromTouches(e.touches);
                        var delta = currentAngle - gestureStartAngle;
                        manualBearing = (gestureStartBearing - delta + 360) % 360;
                        targetBearing = manualBearing;
                    }
                }, { passive: false });
                mapWrap.addEventListener('touchend', function(e) {
                    if (e.touches.length < 2) {
                        isManualMode = false;
                        manualModeTimer = setTimeout(function() {
                            useManualBearing = false;
                            locked = true;
                        }, 5000);
                    }
                });
            }
        }

        function refreshDistanceDisplay() {
            if (appState !== 'arriving' && appState !== 'ready') return;
            if (!map || !ORDER_DATA) return;
            var distEl = document.getElementById('distanceToClient');
            var timeEl = document.getElementById('timeToClient');
            if (!distEl || !timeEl) return;
            var d = 0;
            if (lastDriverLocation && ORDER_DATA.pickup_latitude != null && ORDER_DATA.pickup_longitude != null) {
                d = haversineM(lastDriverLocation.lat, lastDriverLocation.lon, ORDER_DATA.pickup_latitude, ORDER_DATA.pickup_longitude) / 1000;
            }
            if (routeRoadDistanceKm != null && routeRoadDistanceKm > 0) d = routeRoadDistanceKm;
            if (d > MAX_DISTANCE_KM || d < 0 || isNaN(d)) { distEl.textContent = '0.00'; timeEl.textContent = '—'; return; }
            distEl.textContent = d.toFixed(2);
            timeEl.textContent = '~' + Math.max(1, Math.round(d / AVG_SPEED_KMH * 60));
        }
        function fitBoundsToMarkers() {
            if (!map) return;
            const points = [];
            if (clientMarker && clientMarker.getLngLat) {
                var c = clientMarker.getLngLat();
                points.push([c.lng, c.lat]);
            }
            if (driverMarker && driverMarker.getLngLat) {
                var d = driverMarker.getLngLat();
                points.push([d.lng, d.lat]);
            }
            if (points.length < 2) return;
            var minLng = points[0][0], maxLng = points[0][0];
            var minLat = points[0][1], maxLat = points[0][1];
            for (var i = 1; i < points.length; i++) {
                var lng = points[i][0], lat = points[i][1];
                if (lng < minLng) minLng = lng;
                if (lng > maxLng) maxLng = lng;
                if (lat < minLat) minLat = lat;
                if (lat > maxLat) maxLat = lat;
            }
            map.fitBounds([[minLng, minLat], [maxLng, maxLat]], {
                padding: { top: 40, right: 40, bottom: 220, left: 40 },
                maxZoom: 16
            });
        }

        function sendDriverLocationToBackend(lat, lng, heading) {
            if (!ORDER_DATA || !ORDER_DATA.driver_id) return;
            var now = Date.now();
            var distMoved = lastSentLocation ? haversineM(lat, lng, lastSentLocation.lat, lastSentLocation.lon) : MIN_DISTANCE_M;
            var distOk = !lastSentLocation || distMoved >= MIN_DISTANCE_M;
            var timeOk = !lastSentLocation || (now - lastSentTime) >= THROTTLE_MS;
            if (!distOk || !timeOk) return;
            lastSentLocation = { lat: lat, lon: lng };
            lastSentTime = now;
            // Snapped koordinatani hisoblash (Turf mavjud bo'lsa)
            var sLat = lat, sLng = lng;
            if (typeof turf !== 'undefined' && _driverRouteLine && _driverRouteLine.geometry) {
                try {
                    var pt = turf.point([lng, lat]);
                    var snapped = turf.nearestPointOnLine(_driverRouteLine, pt, { units: 'kilometers' });
                    if (snapped && snapped.geometry && snapped.geometry.coordinates) {
                        sLng = snapped.geometry.coordinates[0];
                        sLat = snapped.geometry.coordinates[1];
                    }
                } catch (_) {}
            }
            var body = {
                driver_id: ORDER_DATA.driver_id,
                latitude: lat, longitude: lng,
                snapped_latitude: sLat, snapped_longitude: sLng,
                heading: heading
            };
            if (ORDER_ID_CURRENT) body.order_id = parseInt(ORDER_ID_CURRENT, 10);
            fetch(API_BASE_URL + '/api/webapp/update_driver_location?v=' + Date.now(), {
                method: 'POST',
                headers: webappHeaders(),
                body: JSON.stringify(body)
            }).then(function(){}).catch(function(){});
        }
        function startDriverTracking() {
            if (intervals.position != null) return;
            /* Slow networks (Uzbekistan): allow cached pos for faster first fix; longer timeout */
            var opts = { enableHighAccuracy: true, timeout: 25000, maximumAge: 10000 };

            /* Try Telegram LocationManager first (no popup) */
            var tgApp = window.Telegram && window.Telegram.WebApp;
            if (tgApp && tgApp.LocationManager) {
                try {
                    tgApp.LocationManager.init(function() {
                        if (tgApp.LocationManager.isLocationAvailable) {
                            var tgRetryCount = 0;
                            var tgMaxRetries = 3;
                            function tryTgLocation() {
                                tgApp.LocationManager.getLocation(function(loc) {
                                    if (loc && loc.latitude != null && loc.longitude != null) {
                                        tgRetryCount = 0;
                                        var lat = loc.latitude, lng = loc.longitude;
                                        var heading = loc.course != null ? loc.course : null;
                                        var sp = loc.speed != null ? loc.speed * 3.6 : null;
                                        if (sp != null) lastGpsSpeedKmh = sp;
                                        updateDriverMarker(lat, lng, heading || lastHeading);
                                        sendDriverLocationToBackend(lat, lng, heading || lastHeading);
                                    } else if (tgRetryCount < tgMaxRetries) {
                                        tgRetryCount++;
                                        setTimeout(tryTgLocation, 1500);
                                    } else {
                                        if (intervals.position != null) {
                                            clearInterval(intervals.position);
                                            intervals.position = null;
                                        }
                                        _startBrowserGPS(opts);
                                    }
                                });
                            }
                            tryTgLocation();
                            intervals.position = setInterval(tryTgLocation, 2000);
                            return;
                        }
                        _startBrowserGPS(opts);
                    });
                    return;
                } catch (e) {
                    _startBrowserGPS(opts);
                }
            }

            /* Fallback: browser geolocation */
            _startBrowserGPS(opts);
        }

        function _startBrowserGPS(opts) {
            if (!navigator.geolocation) {
                showGpsError("GPS ishlamayapti!");
                return;
            }
            var geoTimeout = opts.timeout || 25000;
            var geoTimeoutId = setTimeout(function() {
                if (intervals.position == null) onGeoError({ code: 3, message: "timeout" });
            }, geoTimeout + 2000);
            navigator.geolocation.getCurrentPosition(
                function(position) {
                    clearTimeout(geoTimeoutId);
                    var lat = position.coords.latitude;
                    var lng = position.coords.longitude;
                    var sp = position.coords.speed;
                    if (sp != null && !isNaN(sp)) lastGpsSpeedKmh = sp * 3.6;
                    var h = 0;
                    if (ORDER_DATA && ORDER_DATA.pickup_latitude != null) {
                        h = calcBearing(lat, lng, ORDER_DATA.pickup_latitude, ORDER_DATA.pickup_longitude);
                    } else if (ORDER_DATA && ORDER_DATA.destination_latitude != null) {
                        h = calcBearing(lat, lng, ORDER_DATA.destination_latitude, ORDER_DATA.destination_longitude);
                    }
                    updateDriverMarker(lat, lng, h);
                    sendDriverLocationToBackend(lat, lng, h);
                    intervals.position = navigator.geolocation.watchPosition(
                        function(pos) {
                            var la = pos.coords.latitude, ln = pos.coords.longitude;
                            var heading = pos.coords.heading;
                            var sp = pos.coords.speed;
                            if (sp != null && !isNaN(sp)) lastGpsSpeedKmh = sp * 3.6;
                            if (heading == null || isNaN(heading)) {
                                if (lastDriverLocation && lastDriverLocation.lat != null) {
                                    var d = haversineM(la, ln, lastDriverLocation.lat, lastDriverLocation.lon);
                                    if (d > 2) heading = calcBearing(lastDriverLocation.lat, lastDriverLocation.lon, la, ln);
                                    else heading = lastHeading;
                                } else heading = lastHeading;
                            }
                            updateDriverMarker(la, ln, heading);
                            sendDriverLocationToBackend(la, ln, heading);
                        },
                        function(err) { onGeoError(err); },
                        { enableHighAccuracy: true, timeout: 15000, maximumAge: 5000 }
                    );
                },
                function(error) {
                    clearTimeout(geoTimeoutId);
                    onGeoError(error);
                },
                opts
            );
        }
        function onGeoError(error) {
            intervals.position = null;
            hideGpsModal();
            var eo = document.getElementById('errorOverlay'); if (eo) { eo.classList.remove('visible'); }
            var el = document.getElementById('distanceToClient');
            if (el) el.textContent = '—';
            el = document.getElementById('timeToClient');
            if (el) el.textContent = '—';
            document.getElementById('loading').classList.add('hidden');
            if (map && ORDER_DATA && isValidCoord(ORDER_DATA.pickup_latitude, ORDER_DATA.pickup_longitude)) {
                map.easeTo({
                    center: [ORDER_DATA.pickup_longitude, ORDER_DATA.pickup_latitude],
                    zoom: 18,
                    duration: 0
                });
            }
            if (!simOn && routeCoordinates.length >= 2) startSim();
        }
        function showGpsError(msg) {
            intervals.position = null;
            var el = document.getElementById('distanceToClient');
            if (el) el.textContent = '—';
            el = document.getElementById('timeToClient');
            if (el) el.textContent = '—';
            document.getElementById('loading').classList.add('hidden');
            showGpsModal();
        }

        function setTurnAndDistFromDriver(driverPos) {
            if (!driverPos || !routeCoordinates.length || !routeInstructions.length) return;
            var toLatLng = function(c) { return c && (c.lat != null) ? { lat: c.lat, lng: c.lng } : { lat: c[0], lng: c[1] }; };
            var bestIdx = 0, bestD = 1e9;
            for (var i = 0; i < routeCoordinates.length; i++) {
                var p = toLatLng(routeCoordinates[i]);
                var d = haversineM(driverPos.lat, driverPos.lng, p.lat, p.lng);
                if (d < bestD) { bestD = d; bestIdx = i; }
            }
            var nextInst = null;
            for (var j = 0; j < routeInstructions.length; j++) {
                var inst = routeInstructions[j];
                var idx = inst.index != null ? inst.index : (inst.intersection_index != null ? inst.intersection_index : j);
                if (idx > bestIdx) { nextInst = inst; break; }
            }
            if (!nextInst) nextInst = routeInstructions[routeInstructions.length - 1];
            var instIdx = nextInst.index != null ? nextInst.index : (nextInst.intersection_index != null ? nextInst.intersection_index : routeCoordinates.length - 1);
            for (var k = 0; k < routeInstructions.length; k++) { if (routeInstructions[k] === nextInst) { turnI = k; break; } }
            var turnCoord = routeCoordinates[Math.min(instIdx, routeCoordinates.length - 1)];
            var t = toLatLng(turnCoord);
            distKm = turnCoord ? haversineM(driverPos.lat, driverPos.lng, t.lat, t.lng) / 1000 : 0;
        }
        function updateDriverMarker(lat, lng, heading) {
            try {
                if (!map || !ORDER_DATA) return;
                if (!isValidCoord(lat, lng)) return;
                // Route not loaded yet AND marker already created — queue and wait.
                // The first call (driverMarker is undefined/falsy) must fall through so
                // it can call addDriverMarker() and drawRoute(), which triggers the OSRM
                // fetch that eventually sets _driverRouteLine.
                // IMPORTANT: use truthiness check (not !== null) because driverMarker is
                // declared with `let` and starts as `undefined`. `undefined !== null` is
                // true in JS, so `!== null` would fire on the very first GPS update and
                // recreate the deadlock (marker never created, route never fetched).
                if (_driverRouteLine === null && driverMarker) {
                    _pendingGps = { lat: lat, lng: lng, heading: heading };
                    return;
                }
                var _prevSnappedLat = tLat, _prevSnappedLng = tLng;
                var sl = lat, sa = lng;
                if (typeof turf !== 'undefined' && _driverRouteLine && _driverRouteLine.geometry) {
                    try {
                        var _snapPt = turf.point([lng, lat]);
                        var _snapRes = turf.nearestPointOnLine(_snapRouteLine || _driverRouteLine, _snapPt, { units: 'kilometers' });
                        if (_snapRes && _snapRes.geometry && _snapRes.geometry.coordinates) {
                            sa = _snapRes.geometry.coordinates[0]; // lon
                            sl = _snapRes.geometry.coordinates[1]; // lat
                            // Turf returns the exact segment index — use it directly.
                            // The old vertex-search loop found the nearest START node which is wrong
                            // when the projection point is near a segment's end (off-by-one → wrong DR).
                            if (_snapRes.properties && _snapRes.properties.index != null) {
                                _routeAnchorIdx = Math.min(_snapRes.properties.index,
                                    _driverRouteCoords.length > 1 ? _driverRouteCoords.length - 2 : 0);
                                // Rebuild trimmed snap line: snapped point + all vertices ahead.
                                // Starting from the exact snapped coordinate (not segment start vertex)
                                // ensures the next snap cannot project backward even by one segment.
                                var _trimCoords = [[sa, sl]].concat(_driverRouteCoords.slice(_routeAnchorIdx + 1));
                                if (_trimCoords.length >= 2) {
                                    try { _snapRouteLine = turf.lineString(_trimCoords); } catch (_) {}
                                }
                            }
                            _firstSnapDone = true;
                        }
                    } catch (_e) {
                        if (routeCoordinates && routeCoordinates.length >= 2) {
                            var _fb = snapToRoute(lat, lng);
                            sl = _fb[0]; sa = _fb[1]; _routeAnchorIdx = _fb[2];
                        }
                    }
                } else if (routeCoordinates && routeCoordinates.length >= 2) {
                    var _fb2 = snapToRoute(lat, lng);
                    sl = _fb2[0]; sa = _fb2[1]; _routeAnchorIdx = _fb2[2];
                }
                // Adaptive dead zone: tezlikka qarab (2m..7m) GPS noise filtri
                // Bypassed on the first snap so a raw-GPS anchor can never be frozen onto
                // the route line — prevTLat/Lng is guaranteed clean (on-route) from here on.
                var prevTLat = tLat, prevTLng = tLng;
                if (_firstSnapDone && prevTLat != null && prevTLng != null) {
                    var snapMoveDist = haversineM(sl, sa, prevTLat, prevTLng);
                    var _dzThresh = Math.max(2.0, Math.min(spd * 0.15, 7.0));
                    if (snapMoveDist < _dzThresh) {
                        sl = prevTLat;
                        sa = prevTLng;
                    }
                }
                var driverPos = { lat: sl, lng: sa };
                var now = Date.now();
                var speedKmh = 0;
                if (lastDriverLocation && lastPositionTime) {
                    var distM = haversineM(lat, lng, lastDriverLocation.lat, lastDriverLocation.lon);
                    var dtSec = (now - lastPositionTime) / 1000;
                    if (dtSec > 0.1) speedKmh = (distM / 1000) / dtSec * 3600;
                }
                if (lastGpsSpeedKmh != null && !isNaN(lastGpsSpeedKmh) && lastGpsSpeedKmh > 0) speedKmh = lastGpsSpeedKmh;
                lastPositionTime = now;
                lastDriverLocation = { lat: lat, lon: lng };
                pLat = lat;
                pLng = lng;
                tLat = sl;
                tLng = sa;
                spd = speedKmh;
                // Velocity estimation with EMA smoothing at GPS rate.
                // Raw velocity = Δsnapped / Δt_gps. One noisy GPS fix can spike ±27 km/h
                // on the raw estimate; EMA filters this without staling the prediction.
                // α_vel: 0.4 at low speed (τ≈4s at 2s GPS rate) → 0.7 at 20+ km/h (τ≈1.5s).
                // Conversion: τ = -Δt / ln(1-α). α=0.4 @ Δt=2s → τ=3.9s. α=0.7 → τ=1.5s.
                // Zeroed below 3 km/h so parked GPS noise never feeds the prediction.
                var _drDtSec = _gpsAnchorMs > 0 ? (now - _gpsAnchorMs) / 1000 : 0;
                if (_gpsAnchorLat !== null && _drDtSec > 0.1 && speedKmh > 3) {
                    var _rawVelLat = (sl - _gpsAnchorLat) / _drDtSec;
                    var _rawVelLng = (sa - _gpsAnchorLng) / _drDtSec;
                    var _alphaVel = 0.4 + 0.3 * Math.min(speedKmh / 20, 1);
                    _smoothVelLat += (_rawVelLat - _smoothVelLat) * _alphaVel;
                    _smoothVelLng += (_rawVelLng - _smoothVelLng) * _alphaVel;
                    _velLat = _smoothVelLat;
                    _velLng = _smoothVelLng;
                } else {
                    _smoothVelLat = 0; _smoothVelLng = 0;
                    _velLat = 0; _velLng = 0;
                }
                // _routeAnchorIdx is now set at snap time (from Turf's properties.index or
                // snapToRoute's return value). No secondary vertex search needed here.
                _gpsAnchorLat = sl;
                _gpsAnchorLng = sa;
                _gpsAnchorMs = now;
                updateProgressiveRoute(sa, sl);
                // Bearing: smooth blend between route-tangent (low speed) and coordinate
                // (high speed + sufficient movement). Replaces the hard 8 km/h cut.
                // _speedW: 0 at ≤5 km/h → 1 at ≥15 km/h.
                // _distW:  0 at ≤3 m moved → 1 at ≥10 m moved.
                // _coordW = _speedW × _distW: BOTH conditions must be met for coordinate bearing.
                // Below 3 km/h the block is skipped entirely — bearing is frozen.
                if (_prevSnappedLat != null && _prevSnappedLng != null && speedKmh >= 3) {
                    var _moveDist = haversineM(sl, sa, _prevSnappedLat, _prevSnappedLng);
                    var _tangentBrg = (typeof turf !== 'undefined' && _driverRouteLine)
                        ? getRouteTangentBearing(sa, sl) : null;
                    var _speedW = Math.min(Math.max((speedKmh - 5) / 10, 0), 1);
                    var _distW  = Math.min(Math.max((_moveDist - 3) / 7, 0), 1);
                    var _coordW = _speedW * _distW;
                    var _coordBrg = _moveDist >= 3 ? calcBearing(_prevSnappedLat, _prevSnappedLng, sl, sa) : brg;
                    var _tangBrg  = _tangentBrg !== null ? _tangentBrg : brg;
                    var _blendDiff = ((_coordBrg - _tangBrg + 540) % 360) - 180;
                    var _blended  = (_tangBrg + _blendDiff * _coordW + 360) % 360;
                    var _delta = Math.abs(((_blended - brg + 540) % 360) - 180);
                    if (_delta >= 1) brg = _blended;
                }
                if (!driverMarker) {
                    var _tangentInit = (typeof turf !== 'undefined' && _driverRouteLine)
                        ? getRouteTangentBearing(sa, sl) : null;
                    var _initBrg = _tangentInit !== null ? _tangentInit
                        : ((_prevSnappedLat != null && _prevSnappedLng != null)
                            ? calcBearing(_prevSnappedLat, _prevSnappedLng, sl, sa) : brg);
                    brg = _initBrg;
                    displayHeading = _initBrg;
                    displayBearing = _initBrg;
                    targetBearing = _initBrg;
                    addDriverMarker(sl, sa);
                    dLat = sl;
                    dLng = sa;
                    map.flyTo({ center: [sa, sl], zoom: 18 });
                    var pickLat = ORDER_DATA.pickup_latitude;
                    var pickLon = ORDER_DATA.pickup_longitude;
                    if (pickLat != null && pickLon != null) drawRoute(driverPos, { lat: pickLat, lng: pickLon });
                    document.getElementById('loading').classList.add('hidden');
                }
                setTurnAndDistFromDriver(driverPos);
                if (!routeCoordinates.length) {
                    if (ORDER_DATA.pickup_latitude != null && ORDER_DATA.pickup_longitude != null) {
                        distKm = haversineM(driverPos.lat, driverPos.lng, ORDER_DATA.pickup_latitude, ORDER_DATA.pickup_longitude) / 1000;
                    }
                }
                updateNavUI();
                if (appState === 'arriving' || appState === 'ready') {
                    var clPos = (clientMarker && clientMarker.getLngLat) ? clientMarker.getLngLat() : { lat: ORDER_DATA.pickup_latitude, lng: ORDER_DATA.pickup_longitude };
                    if (clPos) {
                        var straightM = haversineM(driverPos.lat, driverPos.lng, clPos.lat, clPos.lng);
                        var d = (routeRoadDistanceKm != null && routeRoadDistanceKm > 0) ? routeRoadDistanceKm : (straightM / 1000);
                        if (d > MAX_DISTANCE_KM || d < 0 || isNaN(d)) d = 0;
                        var distEl = document.getElementById('distanceToClient');
                        var timeEl = document.getElementById('timeToClient');
                        if (distEl) distEl.textContent = d > MAX_DISTANCE_KM ? '—' : d.toFixed(2);
                        if (timeEl) timeEl.textContent = d > MAX_DISTANCE_KM ? '—' : '~' + Math.max(1, Math.round(d / AVG_SPEED_KMH * 60));
                    }
                }
                if (appState === 'trip' && !tripData.isWaiting) {
                    if (tripData.lastPosition) {
                        var segD = haversineM(
                            driverPos.lat, driverPos.lng,
                            tripData.lastPosition.lat, tripData.lastPosition.lng
                        ) / 1000;
                        var minDist = TARIFF.minDistanceUpdate || 0.02;
                        if (segD >= minDist && segD < 1 && spd > 5) {
                            tripData.distance += segD;
                            updateTaximeter();
                        }
                    }
                    tripData.lastPosition = driverPos;
                }
                checkOffRoute(lat, lng);
            } catch (e) {}
        }

        function startSim() {
            if (simOn || !routeCoordinates.length) return;
            simOn = true;
            var lbl = document.getElementById('sim-lbl');
            if (lbl) lbl.textContent = '⏹';
            simIdx = 0;
            addDriverMarker(routeCoordinates[0].lat || routeCoordinates[0][0], routeCoordinates[0].lng || routeCoordinates[0][1]);
            tLat = routeCoordinates[0].lat || routeCoordinates[0][0];
            tLng = routeCoordinates[0].lng || routeCoordinates[0][1];
            dLat = tLat;
            dLng = tLng;
            pLat = tLat;
            pLng = tLng;
            simTmr = setInterval(tick, 1000);
            tick();
        }
        function stopSim() {
            simOn = false;
            clearInterval(simTmr);
            var lbl = document.getElementById('sim-lbl');
            if (lbl) lbl.textContent = '▶';
        }
        function toggleSim() { simOn ? stopSim() : startSim(); }
        function tick() {
            var coords = routeCoordinates;
            if (!coords || simIdx >= coords.length) { simIdx = 0; }
            var pt = coords[simIdx];
            var la = pt.lat != null ? pt.lat : pt[0];
            var ln = pt.lng != null ? pt.lng : pt[1];
            if (pLat != null) {
                var distM = haversineM(pLat, pLng, la, ln);
                if (distM > 5) brg = calcBearing(pLat, pLng, la, ln);
            }
            spd = 28 + Math.sin(simIdx * 0.6) * 18;
            pLat = la;
            pLng = ln;
            tLat = la;
            tLng = ln;
            var pr = simIdx / coords.length;
            distKm = Math.max(0, (routeRoadDistanceKm || 1) * (1 - pr));
            setTurnAndDistFromDriver({ lat: la, lng: ln });
            simIdx++;
            updateNavUI();
        }

        function buildRouteGeoJSON(coords) {
            return {
                type: 'FeatureCollection',
                features: [{
                    type: 'Feature',
                    geometry: {
                        type: 'LineString',
                        coordinates: coords.map(function(c) {
                            var la = c.lat != null ? c.lat : c[0];
                            var ln = c.lng != null ? c.lng : c[1];
                            return [ln, la];
                        })
                    },
                    properties: {}
                }]
            };
        }

        function safeAddRouteLayer(routeGeoJSON) {
            if (map.getSource('route')) {
                map.getSource('route').setData(routeGeoJSON);
            } else {
                var addLayers = function() {
                    if (map.getSource('route')) {
                        map.getSource('route').setData(routeGeoJSON);
                        return;
                    }
                    map.addSource('route', { type: 'geojson', data: routeGeoJSON });
                    map.addLayer({
                        id: 'route-shadow',
                        type: 'line', source: 'route',
                        layout: {'line-join':'round','line-cap':'round'},
                        paint: {'line-color':'rgba(0,0,0,0.3)','line-width':22,'line-blur':3}
                    });
                    map.addLayer({
                        id: 'route-border',
                        type: 'line', source: 'route',
                        layout: {'line-join':'round','line-cap':'round'},
                        paint: {'line-color':'#9A6500','line-width':17}
                    });
                    map.addLayer({
                        id: 'route-main',
                        type: 'line', source: 'route',
                        layout: {'line-join':'round','line-cap':'round'},
                        paint: {'line-color':'#FFD600','line-width':12}
                    });
                    map.addLayer({
                        id: 'route-hi',
                        type: 'line', source: 'route',
                        layout: {'line-join':'round','line-cap':'round'},
                        paint: {'line-color':'rgba(255,255,255,0.5)','line-width':4}
                    });
                };
                if (map.isStyleLoaded && map.isStyleLoaded()) {
                    addLayers();
                } else {
                    map.once('load', addLayers);
                }
            }
        }

        function safeAddRouteABLayer(routeGeoJSON) {
            if (map.getSource('route-ab')) {
                map.getSource('route-ab').setData(routeGeoJSON);
            } else {
                var addLayers = function() {
                    if (map.getSource('route-ab')) {
                        map.getSource('route-ab').setData(routeGeoJSON);
                        return;
                    }
                    map.addSource('route-ab', { type: 'geojson', data: routeGeoJSON });
                    map.addLayer({
                        id: 'route-ab-main',
                        type: 'line', source: 'route-ab',
                        layout: {'line-join':'round','line-cap':'round'},
                        paint: {'line-color':'#276EF1','line-width':10}
                    });
                };
                if (map.isStyleLoaded && map.isStyleLoaded()) {
                    addLayers();
                } else {
                    map.once('load', addLayers);
                }
            }
        }

        function drawRoute(from, to) {
            if (!map || !from || !to) return;
            routeRoadDistanceKm = null;
            routeInstructions = [];
            routeCoordinates = [];

            // from: L.LatLng yoki {lat, lng} bo‘lishi mumkin
            var fromLat = from.lat != null ? from.lat : from[0];
            var fromLng = from.lng != null ? from.lng : from[1];
            var toLat = to.lat != null ? to.lat : to[0];
            var toLng = to.lng != null ? to.lng : to[1];

            var url = 'https://router.project-osrm.org/route/v1/driving/' +
                fromLng + ',' + fromLat + ';' + toLng + ',' + toLat +
                '?overview=full&geometries=geojson&steps=true';

            var controller = new AbortController();
            var timeoutId = setTimeout(function() { controller.abort(); }, 8000);

            fetch(url, { signal: controller.signal })
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    clearTimeout(timeoutId);
                    if (!data || !data.routes || !data.routes.length) {
                        fallbackStraightLine(fromLat, fromLng, toLat, toLng);
                        return;
                    }
                    var r = data.routes[0];
                    routeRoadDistanceKm = (r.distance || 0) / 1000;
                    routeInstructions = [];
                    routeCoordinates = [];
                    if (r.legs && r.legs.length) {
                        r.legs.forEach(function(leg) {
                            if (leg.steps) {
                                leg.steps.forEach(function(step, idx) {
                                    routeInstructions.push({
                                        text: step.name || '',
                                        type: (step.maneuver && typeof step.maneuver.type === 'number') ? step.maneuver.type : -1,
                                        index: step.intersection_index != null ? step.intersection_index : idx
                                    });
                                });
                            }
                        });
                    }
                    if (r.geometry && r.geometry.coordinates) {
                        routeCoordinates = r.geometry.coordinates.map(function(c) { return [c[1], c[0]]; }); // [lat,lng]
                        _driverRouteCoords = r.geometry.coordinates.slice(); // [lon,lat] GeoJSON tartib
                    }
                    if (!routeCoordinates.length) {
                        fallbackStraightLine(fromLat, fromLng, toLat, toLng);
                        return;
                    }
                    // Turf line feature qurish (snapping va progressive trim uchun)
                    if (typeof turf !== 'undefined' && _driverRouteCoords.length >= 2) {
                        try { _driverRouteLine = turf.lineString(_driverRouteCoords); } catch (_) {}
                    }
                    _snapRouteLine = _driverRouteLine;
                    // Replay any GPS update that arrived before the route was ready.
                    if (_pendingGps !== null) {
                        var _pg = _pendingGps; _pendingGps = null;
                        updateDriverMarker(_pg.lat, _pg.lng, _pg.heading);
                    }
                    var routeGeoJSON = buildRouteGeoJSON(routeCoordinates);
                    safeAddRouteLayer(routeGeoJSON);
                    setTurnAndDistFromDriver({ lat: fromLat, lng: fromLng });
                    updateNavUI();
                })
                .catch(function() {
                    clearTimeout(timeoutId);
                    fallbackStraightLine(fromLat, fromLng, toLat, toLng);
                });
        }

        /**
         * Progressive trim: haydovchi o'tib ketgan yo'l qismini o'chirib,
         * faqat haydovchidan pickup gacha sariq chiziqni xaritada ko'rsatadi.
         * driverLon, driverLat — snapped yoki GPS koordinatalar [lon, lat].
         */
        function updateProgressiveRoute(driverLon, driverLat) {
            if (typeof turf === 'undefined') return;
            if (!_driverRouteLine || !_driverRouteCoords || _driverRouteCoords.length < 2) return;
            try {
                var drvPt = turf.point([driverLon, driverLat]);
                var snapped = turf.nearestPointOnLine(_driverRouteLine, drvPt, { units: 'kilometers' });
                if (!snapped || !snapped.geometry) return;
                // Manzil (pickup) = marshrutning oxirgi nuqtasi [lon, lat]
                var destCoord = _driverRouteCoords[_driverRouteCoords.length - 1];
                var destPt = turf.point(destCoord);
                // Haydovchi dan manzilga qadar qolgan yo'l
                var remaining = turf.lineSlice(snapped, destPt, _driverRouteLine);
                if (!remaining || !remaining.geometry || !remaining.geometry.coordinates || remaining.geometry.coordinates.length < 2) return;
                // [lon,lat] → [lat,lng] konversiya
                var trimCoords = remaining.geometry.coordinates.map(function(c) { return [c[1], c[0]]; });
                var geo = buildRouteGeoJSON(trimCoords);
                safeAddRouteLayer(geo);
            } catch (_) {}
        }

        function fallbackStraightLine(fromLat, fromLng, toLat, toLng) {
            routeCoordinates = [[fromLat, fromLng], [toLat, toLng]];
            // Build _driverRouteLine so the queue gate is satisfied and snapping works
            // on the straight-line fallback exactly the same as on a real OSRM route.
            _driverRouteCoords = [[fromLng, fromLat], [toLng, toLat]];
            if (typeof turf !== 'undefined' && _driverRouteCoords.length >= 2) {
                try { _driverRouteLine = turf.lineString(_driverRouteCoords); } catch (_) {}
            }
            _snapRouteLine = _driverRouteLine;
            routeRoadDistanceKm = haversineM(fromLat, fromLng, toLat, toLng) / 1000;
            routeInstructions = [{ text: "To'g'ri yo'l", type: -1, index: 0 }];
            var routeGeoJSON = buildRouteGeoJSON(routeCoordinates);
            safeAddRouteLayer(routeGeoJSON);
            safeAddRouteABLayer(routeGeoJSON);
            setTurnAndDistFromDriver({ lat: fromLat, lng: fromLng });
            updateNavUI();
            if (_pendingGps !== null) {
                var _pg = _pendingGps; _pendingGps = null;
                updateDriverMarker(_pg.lat, _pg.lng, _pg.heading);
            }
        }

        /**
         * Off-route detection: called after every GPS update during a trip.
         * Uses turf.pointToLineDistance to measure perpendicular distance from
         * the raw GPS fix to _driverRouteLine. If > 70 m and the 5-second
         * cooldown has elapsed, a fresh OSRM route is requested and the map
         * polyline is replaced. Snap state is reset so the driver snaps cleanly
         * to the new route on the next GPS update.
         */
        function checkOffRoute(lat, lng) {
            if (appState !== 'trip') return;
            if (typeof turf === 'undefined') return;
            if (!_driverRouteLine || !_driverRouteLine.geometry) return;
            if (!ORDER_DATA ||
                !isValidCoord(ORDER_DATA.destination_latitude, ORDER_DATA.destination_longitude)) return;
            if (Date.now() - _lastRerouteMs < 5000) return;

            try {
                var distM = turf.pointToLineDistance(
                    turf.point([lng, lat]),
                    _driverRouteLine,
                    { units: 'meters' }
                );
                if (distM > 70) {
                    _lastRerouteMs = Date.now();
                    // Reset snap state so next GPS anchors to the new route.
                    _firstSnapDone = false;
                    _routeAnchorIdx = 0;
                    _snapRouteLine = null;
                    drawRoute(
                        { lat: lat, lng: lng },
                        { lat: ORDER_DATA.destination_latitude, lng: ORDER_DATA.destination_longitude }
                    );
                }
            } catch (_) {}
        }

        function drawRouteAB(fromA, toB) {
            if (!map || !fromA || !toB) return;
            var fromLat = fromA.lat != null ? fromA.lat : fromA[0];
            var fromLng = fromA.lng != null ? fromA.lng : fromA[1];
            var toLat = toB.lat != null ? toB.lat : toB[0];
            var toLng = toB.lng != null ? toB.lng : toB[1];
            var coords = [
                [fromLat, fromLng],
                [toLat, toLng]
            ];
            var routeGeoJSON = buildRouteGeoJSON(coords);
            safeAddRouteABLayer(routeGeoJSON);
        }

        async function handleArrived() {
            appState = 'ready';

            /* API call — mijozga xabar */
            try {
                var arrUrl = API_BASE_URL + '/api/webapp/order/' + ORDER_ID_CURRENT + '/arrived?v=' + Date.now();
                if (WEBAPP_TOKEN) arrUrl += '&token=' + encodeURIComponent(WEBAPP_TOKEN);
                var resp = await fetch(arrUrl, {
                    method: 'POST',
                    headers: webappHeaders()
                });
                var result = await resp.json();
                if (result.ok) {
                    console.log("Mijozga xabar yuborildi");
                }
            } catch (e) {
                console.log("Xabar yuborishda xato:", e);
            }

            /* UI yangilash */
            var lbl = document.getElementById('destPinLabel');
            if (lbl) lbl.textContent = 'FINISH';
            document.getElementById('arrivedBtn').style.display = 'none';
            document.getElementById('startTripBtn').style.display = 'block';

            /* Bottom panel matnini yangilash */
            var distLabel = document.querySelector('.distance-label');
            if (distLabel) distLabel.textContent = 'MANZILGACHA';
        }

        async function handleStartTrip() {
            if (!map) return;
            var hasDriverLoc = driverMarker && typeof driverMarker.getLngLat === 'function';
            try { if (hasDriverLoc) driverMarker.getLngLat(); } catch (_) { hasDriverLoc = false; }
            if (!hasDriverLoc) {
                if (ORDER_DATA && isValidCoord(ORDER_DATA.pickup_latitude, ORDER_DATA.pickup_longitude)) {
                    map.easeTo({
                        center: [ORDER_DATA.pickup_longitude, ORDER_DATA.pickup_latitude],
                        zoom: 15,
                        duration: 0
                    });
                }
                var msg = "Lokatsiya kutilmoqda. GPS yoqilganligini tekshiring va biroz kuting.";
                if (window.Telegram && window.Telegram.WebApp && window.Telegram.WebApp.showAlert) {
                    window.Telegram.WebApp.showAlert(msg);
                } else {
                    alert(msg);
                }
                return;
            }
            try {
                var posStart = driverMarker.getLngLat();
                var startUrl = API_BASE_URL + '/api/webapp/order/' + ORDER_ID_CURRENT + '/status?new_status=started&v=' + Date.now();
                startUrl += '&lat=' + encodeURIComponent(posStart.lat) + '&lon=' + encodeURIComponent(posStart.lng);
                if (WEBAPP_TOKEN) startUrl += '&token=' + encodeURIComponent(WEBAPP_TOKEN);
                await fetch(startUrl, { method: 'POST', headers: webappHeaders() });
            } catch (e) { console.log("Status update xato:", e); }
            document.body.classList.add('taximeter-mode');
            appState = 'trip';
            /* Draw route from current position to destination */
            if (ORDER_DATA &&
                ORDER_DATA.destination_latitude != null &&
                ORDER_DATA.destination_longitude != null &&
                dLat != null && dLng != null) {
                var fromPos = { lat: dLat, lng: dLng };
                var toPos = {
                    lat: ORDER_DATA.destination_latitude,
                    lng: ORDER_DATA.destination_longitude
                };
                drawRoute(fromPos, toPos);
            }
            document.getElementById('arrivingPanel').style.display = 'none';
            document.getElementById('taximeterScreen').classList.add('active');
            document.getElementById('map').classList.add('minimized');
            var nav = ['top-bar', 'nav-bottom', 'compassBtn'];
            for (var i = 0; i < nav.length; i++) {
                var el = document.getElementById(nav[i]);
                if (el) el.style.display = 'none';
            }
            /* Explicit hide for compass */
            var compassEl = document.getElementById('compassBtn');
            if (compassEl) {
                compassEl.style.display = 'none';
                compassEl.style.visibility = 'hidden';
                compassEl.style.opacity = '0';
                compassEl.style.pointerEvents = 'none';
            }
            /* Hide MapLibre controls */
            document.querySelectorAll(
                '.maplibregl-ctrl-group, .maplibregl-ctrl-compass'
            ).forEach(function(el) {
                el.style.display = 'none';
            });
            var btn2d3d = document.querySelector('.btn-2d3d');
            if (btn2d3d) btn2d3d.style.display = 'none';
            var pos = driverMarker.getLngLat();
            tripData.lastPosition = { lat: pos.lat, lng: pos.lng };
            intervals.timer = setInterval(updateTimer, 1000);
            updateTaximeter();
            updateSyncUI();
        }

        function toggleWaiting() {
            tripData.isWaiting = !tripData.isWaiting;
            const btn = document.getElementById('waitingBtn');
            btn.textContent = tripData.isWaiting ? '▶ DAVOM ETISH' : '⏸ PAUZA / KUTISH';
            btn.className = tripData.isWaiting ? 'action-btn btn-success' : 'action-btn btn-warning';
        }

        function safeAlert(msg, cb) { alert(msg); if (cb) cb(); }
        function safeConfirm(msg, onOk) { if (confirm(msg)) onOk(); }
        function handleFinish() {
            safeConfirm("Safarni yakunlab, tolovni oldingizmi?", finishTrip);
        }

        async function finishTrip() {
            var orderId = ORDER_ID_CURRENT;
            if (!orderId) { safeAlert("Order ID topilmadi."); return; }
            var finalFare = document.getElementById('currentFare').textContent.replace(/,/g, '');
            var distKm = tripData.distance;
            var fp = parseFloat(finalFare);
            if (isNaN(fp) || fp <= 0) {
                safeAlert("Taksometr narxi noto'g'ri. Sahifani yangilab qayta urinib ko'ring.");
                return;
            }
            var item = {
                orderId: orderId,
                final_price: fp,
                distance_km: distKm,
                token: WEBAPP_TOKEN || '',
                apiBaseUrl: API_BASE_URL
            };
            enqueuePendingTrip(item);
            updateSyncUI();

            document.getElementById('loading').classList.remove('hidden');
            try {
                await flushPendingTrips();
            } finally {
                document.getElementById('loading').classList.add('hidden');
            }

            var stillPending = getPendingTrips().some(function(x) { return String(x.orderId) === String(orderId); });
            if (stillPending) {
                safeAlert("Internet yo'q yoki server javob bermadi. Ma'lumot saqlandi — ulanish tiklanganda avtomatik yuboriladi.");
            }
        }

        function updateTimer() {
            // AGAR PAUZA BO\u0027LSA, UMUMIY VAQTNI OSHIRMAYMIZ
            if (tripData.isWaiting) {
                tripData.waitingTime++; // Faqat kutish vaqtini oshiramiz
            } else {
                tripData.elapsedSeconds++; // Faqat safar vaqtini oshiramiz
            }

            const m = Math.floor(tripData.elapsedSeconds / 60).toString().padStart(2, '0');
            const s = (tripData.elapsedSeconds % 60).toString().padStart(2, '0');
            document.getElementById('tripTime').textContent = `${m}:${s}`;
            
            updateTaximeter();
        }

        function updateTaximeter() {
            const fare = TARIFF.startPrice + (tripData.distance * TARIFF.pricePerKm) + ((tripData.waitingTime / 60) * TARIFF.pricePerMinWaiting);
            const rounded = Math.round(fare / 100) * 100;
            document.getElementById('currentFare').textContent = rounded.toLocaleString('en-US');
            document.getElementById('tripDistance').textContent = tripData.distance.toFixed(2);
        }

        window.addEventListener('online', function() {
            updateSyncUI();
            flushPendingTrips();
        });
        window.addEventListener('offline', function() {
            updateSyncUI();
        });
        document.addEventListener('visibilitychange', function() {
            if (document.visibilityState === 'visible') {
                if (map) map.resize();
                updateSyncUI();
                flushPendingTrips();
            }
        });
        window.addEventListener('resize', function() {
            if (map) map.resize();
        });

        window.onload = init;
    </script>
</body>
</html>
"""

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

# CORS sozlamalari
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def json_exception_handler(request, exc):
    """Return JSON for unhandled exceptions so admin panel can parse error responses."""
    if isinstance(exc, HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    logger.exception("Unhandled exception: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc) if len(str(exc)) < 200 else "Internal server error"},
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
    return HTML_CONTENT.replace("__WEBAPP_BASE_URL__", base_url)

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