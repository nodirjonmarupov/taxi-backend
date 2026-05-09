(function(){
    var tg = (window.Telegram && window.Telegram.WebApp) ? window.Telegram.WebApp : null;
    if (tg) {
        try { tg.ready(); tg.expand(); } catch (_) {}
        if (window.Telegram?.WebApp) {
            try {
                Telegram.WebApp.expand();
                Telegram.WebApp.enableClosingConfirmation();
            } catch (_) {}
        }
    }
    if (location.protocol !== 'https:' && location.hostname !== 'localhost' && location.hostname.indexOf('127.') !== 0) {
        document.body.innerHTML = '<div style="padding:24px;text-align:center;font-size:16px;">Geolocation faqat HTTPS da ishlaydi. Iltimos, xavfsiz manzil orqali oching.</div>';
        throw new Error('HTTPS required');
    }
})();
console.log("JS LOADED OK");
/** Taksometr: narx faqat server /trip-meter estimated_fare dan (hardcoded tariff yo'q). */
let TARIFF = null;
let TARIFF_LOAD_ERROR = false;
let ORDER_DATA = null;
const tg = (window.Telegram && window.Telegram.WebApp) ? window.Telegram.WebApp : { expand: function(){}, ready: function(){} };

let map, driverMarker, clientMarker, destMarker;
let _gRoutePolyline = null;
let _gRouteShadow = null;
let _gRouteAbPolyline = null;
let _gPassedPolyline = null;
let routeRoadDistanceKm = null;
let routeInstructions = [], routeCoordinates = [];
// Turf route line feature (haydovchi uchun snapping; polyline always full route)
let _driverRouteLine = null;       // turf.lineString ??[lon,lat] koordinatlarda
let _driverRouteCoords = [];       // [[lon,lat], ...] — route polyline (GeoJSON tartib)
let _smoothedRouteCoords = null;
let _routeHash = null;
let _smoothedCoordsHash = null;
let _lastRouteUpdateTs = 0;
let _routeRequestId = 0;
let __lastRerouteTs = 0;
let _lastRerouteLat = null;
let _lastRerouteLng = null;
let arrowEl = null;
let tLat = null, tLng = null, dLat = null, dLng = null, brg = 0, spd = 0;
let pLat = null, pLng = null, locked = true;
let simIdx = 0, simOn = false, simTmr = null, turnI = 0, distKm = 1;
let displayBearing = 0, targetBearing = 0;
let displayHeading = 0;
let _camBlockUntil = 0;
let _lastCamLat = null, _lastCamLng = null, _lastCamBrg = 0, _lastCamZoom = 0;
let _camLat = null;
let _camLng = null;
let _lastCamUpdate = 0;
let _userZooming = false;
let _userInteracting = false;
let _isRotating = false;
let _lastUserInteraction = 0;
let _velLat = 0, _velLng = 0;
let _smoothVelLat = 0, _smoothVelLng = 0;
let _gpsAnchorLat = null, _gpsAnchorLng = null, _gpsAnchorMs = 0;
let _predLat = null, _predLng = null;
let _followMode = true;
let _routeAnchorIdx = 0;
let _currentInstructionIndex = 0; // next maneuver in routeInstructions; only advances forward
let _stableZoom = null; // EMA-smoothed zoom; prevents per-frame flicker at speed boundaries
let _zoomInitialized = false;
let _lastNavUpdate = 0;      // throttle nav UI (~10 FPS adaptive)
let _lastPredSnapUpdate = 0; // throttle Turf prediction snap (~10 FPS)
let _lastTurnI = null;       // DOM cache: suppress updateNavUI when nothing changed
let _lastDist = null;
let lastBottomUpdateTs = 0;
let lastBottomDistance = null;
let _displayArrowBrg = null;
let _lastStableLat = null;
let _lastStableLng = null;
let isSnapped = false;
let _pendingGps = null;    // queued GPS update received before _driverRouteLine was ready
let _snapRouteLine = null;  // mirror of full _driverRouteLine (no progressive trim)
let _offRouteCount = 0;       // consecutive GPS samples past off-route threshold (noise filter)
let _lastForceRerouteAt = 0;
const FORCE_REROUTE_MIN_INTERVAL_MS = 1500;

function canForceRerouteNow() {
    const now = Date.now();
    if (now - _lastForceRerouteAt < FORCE_REROUTE_MIN_INTERVAL_MS) return false;
    _lastForceRerouteAt = now;
    return true;
}

let _rerouteInFlight = false; // single in-flight directions request for reroute
// /match pipeline
let _matchInFlight = false;
let _matchCallCount = 0;
let _routeRedrawCount = 0;
let _destOffsetActive = false;
const _GPS_BUFFER_SIZE = 6;
const _gpsMatchBuffer = [];
let _routeInFlight = false;   // global mutex: any drawRoute directions fetch
/** Last successful road route (avoid duplicate Directions calls for tiny GPS jitter). */
let _routeFetchCache = null;
var ROUTE_MIN_API_SEGMENT_M = 50;
var ROUTE_SAME_ENDPOINT_M = 10;
var ROUTE_CACHE_NEAR_M = 50;
var OFF_ROUTE_THRESHOLD_M = 30;
let _lastProgressLat = null;
let _lastProgressLng = null;
let _lastProgressAnchorIdx = null;
let _lastDbgLat = null;
let _lastDbgLng = null;
let _lastRouteSnapUpdate2 = 0;
let _dispLat = null;
let _lastRenderLat = null, _lastRenderLng = null;
let _dispLng = null;
let _dispArrowDeg = null;
let _wakeLock = null;
let _keepAliveInterval = null;
function enableFallbackKeepAlive() {
    if (_keepAliveInterval) return;
    _keepAliveInterval = setInterval(() => {
        // minimal no-op to keep WebView active
        document.body.style.opacity =
            document.body.style.opacity === '1' ? '0.99' : '1';
    }, 20000);
}
function disableFallbackKeepAlive() {
    if (_keepAliveInterval) {
        clearInterval(_keepAliveInterval);
        _keepAliveInterval = null;
    }
}
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
let tripData = { distance: 0, waitingTime: 0, elapsedSeconds: 0, isWaiting: false, lastPosition: null, serverFare: null, surge: 1 };
// UI-only: smooth fare display (serverFare remains source of truth)
let _fareUI = {
    displayed: null,
    target: null,
    from: null,
    startTs: 0,
    durMs: 1100,
    raf: null
};
let _resumeInFlight = false;
let intervals = { timer: null, position: null, tripMeterPoll: null };

const API_BASE_URL = window.__WEBAPP_BASE_URL__ || window.location.origin;
fetch(API_BASE_URL + '/api/webapp/tariff?v=' + Date.now(), { headers: { 'ngrok-skip-browser-warning': '1' } })
    .then(function(r){ if (!r.ok) throw new Error('tariff http'); return r.json(); })
    .then(function(d){
        if (!d || d.startPrice == null || isNaN(Number(d.startPrice))) throw new Error('tariff bad');
        TARIFF = {
            startPrice: Number(d.startPrice),
            pricePerKm: Number(d.pricePerKm),
            pricePerMinWaiting: Number(d.pricePerMinWaiting),
            minDistanceUpdate: d.minDistanceUpdate != null ? Number(d.minDistanceUpdate) : 0.02
        };
    })
    .catch(function(){
        TARIFF_LOAD_ERROR = true;
        try {
            var el = document.getElementById('statusText');
            if (el) el.textContent = "Tarif yuklanmadi. Sahifani yangilang.";
        } catch (_) {}
    });
const urlParams = new URLSearchParams(window.location.search);
const ORDER_ID_CURRENT = urlParams.get('order_id');
const WEBAPP_TOKEN = urlParams.get('token');
function webappHeaders() {
    var h = { 'ngrok-skip-browser-warning': 'true', 'Content-Type': 'application/json' };
    if (WEBAPP_TOKEN) h['X-WebApp-Token'] = WEBAPP_TOKEN;
    return h;
}

function getTripOrderIdForApi() {
    return (ORDER_DATA && ORDER_DATA.id != null) ? ORDER_DATA.id : ORDER_ID_CURRENT;
}

function applyTripMeterPayload(data) {
    console.log("[TRIP_METER_APPLY_BEFORE]", JSON.parse(JSON.stringify(tripData)));
    console.log("[TRIP_METER_PAYLOAD]", data);
    if (data != null) console.log("trip-meter active:", data.active);
    if (!data || !data.active) {
        try {
            console.log("[TRIP_METER_APPLY_AFTER]", JSON.parse(JSON.stringify(tripData)));
        } catch (_e) {
            console.log("[TRIP_METER_APPLY_AFTER]", tripData);
        }
        return;
    }
    if (data.distance_km != null) tripData.distance = data.distance_km;
    if (!tripData.isWaiting) {
        if (data.waiting_seconds != null) tripData.waitingTime = data.waiting_seconds;
    }
    tripData.isWaiting = !!data.is_waiting;
    tripData.surge = (data.surge_multiplier != null && data.surge_multiplier !== undefined)
        ? Number(data.surge_multiplier)
        : (tripData.surge || 1);
    if (data.estimated_fare != null) tripData.serverFare = data.estimated_fare;
    if (data.elapsed_seconds != null && !isNaN(Number(data.elapsed_seconds))) {
        tripData.elapsedSeconds = Number(data.elapsed_seconds) || 0;
    }
    try {
        console.log("[TRIP_METER_APPLY_AFTER]", JSON.parse(JSON.stringify(tripData)));
    } catch (_e2) {
        console.log("[TRIP_METER_APPLY_AFTER]", tripData);
    }
    updateTaximeter();
}

function fetchTripMeterSnapshot() {
    var oid = getTripOrderIdForApi();
    if (!oid || !WEBAPP_TOKEN || appState !== 'trip') return Promise.resolve();
    return fetch(API_BASE_URL + '/api/webapp/order/' + oid + '/trip-meter?v=' + Date.now(), {
        headers: webappHeaders(),
        cache: 'no-store'
    })
        .then(function(r) {
            if (!r.ok) return null;
            return r.json();
        })
        .then(function(data) {
            if (data != null) console.log("[TRIP_METER_FETCH]", data);
            if (data) applyTripMeterPayload(data);
        })
        .catch(function() {});
}

function startTripMeterPolling() {
    if (intervals.tripMeterPoll != null) return;
    intervals.tripMeterPoll = setInterval(function() {
        if (appState === 'trip') fetchTripMeterSnapshot();
    }, 3000);
    if (appState === 'trip') fetchTripMeterSnapshot();
}

function stopTripMeterPolling() {
    if (intervals.tripMeterPoll != null) {
        clearInterval(intervals.tripMeterPoll);
        intervals.tripMeterPoll = null;
    }
}

if (ORDER_ID_CURRENT) console.log("Joriy buyurtma ID:", ORDER_ID_CURRENT);
const MAX_DISTANCE_KM = 500;

var PENDING_TRIPS_KEY = 'pending_trips';
var pendingFlushLock = false;
let _lastSyncTime = 0;

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
    var chatBtn = document.getElementById('chatPulseBanner');
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
    if (chatBtn) {
        var _tripActive = (tripData && (tripData.status === 'in_progress' || tripData.started === true)) ||
            (ORDER_DATA && ORDER_DATA.status === 'in_progress') ||
            appState === 'trip';
        chatBtn.style.display = _tripActive ? 'none' : 'block';
    }
}

async function enableWakeLock() {
    try {
        if ('wakeLock' in navigator && !_wakeLock) {
            _wakeLock = await navigator.wakeLock.request('screen');
            _wakeLock.addEventListener('release', function () {
                _wakeLock = null;
            });
        } else {
            enableFallbackKeepAlive();
        }
    } catch (err) {
        console.warn('WakeLock failed', err);
        enableFallbackKeepAlive();
    }
}

function disableWakeLock() {
    if (_wakeLock) {
        try { _wakeLock.release(); } catch (_) {}
        _wakeLock = null;
    }
    disableFallbackKeepAlive();
}

function sendTripUpdate() {
    if (!ORDER_ID_CURRENT) return;
    if (!WEBAPP_TOKEN) return;
    if (appState !== 'trip') return;
    var distKm = (tripData && typeof tripData.distance === 'number' && !isNaN(tripData.distance)) ? tripData.distance : 0;
    var url = API_BASE_URL + '/api/webapp/order/' + ORDER_ID_CURRENT +
        '/status?new_status=in_progress&distance_km=' + encodeURIComponent(String(distKm)) +
        '&v=' + Date.now();
    fetch(url, { method: 'POST', headers: webappHeaders() }).then(function(){}).catch(function(){});
}

function maybeSyncToServer() {
    var now = Date.now();
    if (now - _lastSyncTime > 7000) {
        sendTripUpdate();
        _lastSyncTime = now;
    }
}
function sendPendingItem(item) {
    var params = new URLSearchParams({ new_status: 'completed' });
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
    stopTripMeterPolling();
    if (ORDER_DATA) ORDER_DATA.status = 'completed';
    var loadingEl = document.getElementById('loading');
    if (loadingEl) loadingEl.classList.add('hidden');
    var finalFareStr = (item.display_fare != null && item.display_fare !== '')
        ? String(item.display_fare)
        : 'server';
    var payload = {
        status: 'finished',
        order_id: parseInt(item.orderId, 10),
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
    try { localStorage.removeItem('trip_active_order_id'); } catch (_) {}
    disableWakeLock();
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
                        /* mijoz xato ??qayta yuborish foydasiz */
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
let headingBuffer = [];
let lastHeading = 0;
let _needsTripRouteRestore = false;
let lastSentLocation = null;
let lastSentTime = 0;
const MIN_DISTANCE_M = 15;
const ROUTE_SNAP_MAX_M = 20;
const HEADING_BUFFER_MAX = 8;
const HEADING_BUFFER_RESET_DEG = 30;
const PREDICT_AHEAD_MIN_S = 0.3;
const PREDICT_AHEAD_MAX_S = 0.5;
const THROTTLE_MS = 7000;
let gpsErrorShown = false;
let navAutoMode = true;
let returnToNavTimer = null;
let _navProgrammatic = false;
let lastPositionTime = null;
let lastGpsSpeedKmh = null;
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

function calculateRemainingDistance(driverLat, driverLng) {
    if (!routeCoordinates || routeCoordinates.length < 2) return 0;
    if (typeof _routeAnchorIdx !== 'number' || isNaN(_routeAnchorIdx)) return 0;
    var start = Math.max(0, Math.min(_routeAnchorIdx, routeCoordinates.length - 1));
    var curLat = driverLat != null && !isNaN(driverLat) ? driverLat : dLat;
    var curLng = driverLng != null && !isNaN(driverLng) ? driverLng : dLng;
    var dist = 0;
    if (curLat != null && curLng != null && !isNaN(curLat) && !isNaN(curLng) && start < routeCoordinates.length) {
        var next = routeCoordinates[start];
        dist += haversineM(curLat, curLng, next[0], next[1]);
    }
    for (var i = start; i < routeCoordinates.length - 1; i++) {
        var a = routeCoordinates[i];
        var b = routeCoordinates[i + 1];
        dist += haversineM(a[0], a[1], b[0], b[1]);
    }
    return dist / 1000;
}

function calculateRemainingTime(distKm) {
    var avgSpeed = 35;
    if (!isFinite(distKm) || distKm < 0 || avgSpeed <= 0) return 0;
    return (distKm / avgSpeed) * 60;
}

function updateBottomPanel(remainingKm, remainingMin) {
    if (appState !== 'arriving' && appState !== 'ready') return;
    var distEl = document.getElementById('distanceToClient');
    var timeEl = document.getElementById('timeToClient');
    if (!distEl || !timeEl) return;
    var rk = remainingKm;
    if (rk > MAX_DISTANCE_KM || isNaN(rk)) {
        distEl.textContent = '0.00';
        timeEl.textContent = '0';
        return;
    }
    distEl.textContent = rk.toFixed(2);
    timeEl.textContent = String(Math.max(0, Math.round(remainingMin)));
}

function _bearing(a, b) {
    var lat1 = a[0] * Math.PI / 180;
    var lat2 = b[0] * Math.PI / 180;
    var dLng = (b[1] - a[1]) * Math.PI / 180;

    var y = Math.sin(dLng) * Math.cos(lat2);
    var x = Math.cos(lat1) * Math.sin(lat2) -
        Math.sin(lat1) * Math.cos(lat2) * Math.cos(dLng);

    var brng = Math.atan2(y, x) * 180 / Math.PI;
    return (brng + 360) % 360;
}

function _normalizeAngle(deg) {
    while (deg > 180) deg -= 360;
    while (deg <= -180) deg += 360;
    return deg;
}

function getTurnIcon(delta) {
    if (delta > 25) return "⬅️";
    if (delta < -25) return "➡️";
    return "⬆️";
}

function formatDistance(meters) {
    if (meters < 1000) return Math.round(meters) + " m";
    return (meters / 1000).toFixed(1) + " km";
}

function buildPolylineManeuvers(coords) {
    if (!coords || coords.length < 1) return [];
    if (coords.length < 3) {
        return [{
            text: "🎯 Manzilga yetdingiz",
            type: -1,
            index: coords.length - 1
        }];
    }

    var TURN_MIN_DEG = 25;
    var maneuvers = [];

    for (var i = 1; i < coords.length - 1; i++) {
        var A = coords[i - 1];
        var B = coords[i];
        var C = coords[i + 1];

        var b1 = _bearing(A, B);
        var b2 = _bearing(B, C);

        var delta = _normalizeAngle(b2 - b1);

        if (Math.abs(delta) < TURN_MIN_DEG) continue;

        var lastIdx = maneuvers.length ? maneuvers[maneuvers.length - 1].index : -1000;
        if (i - lastIdx < 5) continue;

        var icon = getTurnIcon(delta);
        var text = icon + " " + (delta > 0 ? "Chapga buriling" : "O'ngga buriling");

        maneuvers.push({
            text: text,
            type: 1,
            index: i
        });
    }

    maneuvers.push({
        text: "🎯 Manzilga yetdingiz",
        type: -1,
        index: coords.length - 1
    });

    return maneuvers;
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
// Stays on road geometry through curves ??superior to linear extrapolation.
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
// Without this correction, 1째 lon ??84 km at lat 41째 vs 1째 lat ??111 km ??24%
// projection error ??marker consistently offset from road.
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

function _mapsJsReady() {
    return typeof google !== 'undefined' && google.maps && google.maps.Map;
}
function initGoogleMap(initialLat, initialLng) {
    var el = document.getElementById('map');
    if (!el || !_mapsJsReady()) throw new Error('Google Maps not loaded');
    map = new google.maps.Map(el, {
        center: { lat: initialLat, lng: initialLng },
        zoom: 17,
        disableDefaultUI: true,
        gestureHandling: 'greedy',
        zoomControl: true,
        disableDoubleClickZoom: false,
        scrollwheel: true,
        clickableIcons: false,
        mapTypeId: 'roadmap',
        renderingType: google.maps.RenderingType.VECTOR,
        tilt: 45,
        heading: 0,
        isFractionalZoomEnabled: true,
        headingInteractionEnabled: true
    });
    if (!_zoomInitialized) {
        try { map.setZoom(17); } catch (_) {}
        _zoomInitialized = true;
    }
    map.addListener('zoom_changed', function () {
        _userZooming = true;

        setTimeout(function () {
            _userZooming = false;
        }, 2000);
    });
    map.addListener('zoom_changed', function () {
        _userInteracting = true;
        _lastUserInteraction = Date.now();
    });
    map.addListener('dragstart', function () {
        _userInteracting = true;
        _lastUserInteraction = Date.now();
    });
    map.addListener('heading_changed', function () {
        if (_userInteracting) {   // only user gesture, not programmatic
            _isRotating = true;
        }
        _lastUserInteraction = Date.now();
    });
    // Attempt to hide POIs/transit. In VECTOR mode this may be ignored (acceptable).
    try {
        map.setOptions({
            styles: [
                { featureType: 'poi', stylers: [{ visibility: 'off' }] },
                { featureType: 'transit', stylers: [{ visibility: 'off' }] }
            ]
        });
    } catch (e) { console.warn('map.setOptions(styles) failed', e); }
    google.maps.event.addListenerOnce(map, 'tilesloaded', function() {
        try { map.setTilt(45); } catch (e) { console.warn('map.setTilt failed (tilesloaded)', e); }
    });
    try { map.setTilt(45); } catch (e) { console.warn('map.setTilt failed (init)', e); }
    return map;
}
function mapResize() {
    if (map && _mapsJsReady()) {
        try { google.maps.event.trigger(map, 'resize'); } catch (_) {}
    }
}
function mapEaseToCamera(opts) {
    if (_followMode) return;   // disable during navigation
    if (!map || !_mapsJsReady()) return;
    var c = opts.center;
    var lat = Array.isArray(c) ? c[1] : c.lat;
    var lng = Array.isArray(c) ? c[0] : c.lng;
    var ll = new google.maps.LatLng(lat, lng);
    var dur = opts.duration != null ? opts.duration : 350;
    if (dur === 0) {
        map.setCenter(ll);
        try { if (opts.bearing != null) map.setHeading(opts.bearing); } catch (_) {}
        try { if (opts.pitch != null) map.setTilt(opts.pitch); } catch (_) {}
        return;
    }
    map.setCenter(ll);
    try { if (opts.bearing != null) map.setHeading(opts.bearing); } catch (_) {}
    try { if (opts.pitch != null) map.setTilt(opts.pitch); } catch (_) {}
}
function updateCamera(lat, lng, heading) {
    if (!map || !_mapsJsReady()) return;

    if (_camLat === null) {
        _camLat = lat;
        _camLng = lng;
    }

    // smooth follow
    _camLat += (lat - _camLat) * 0.12;
    _camLng += (lng - _camLng) * 0.12;

    // forward offset (stable, small)
    var z = map.getZoom ? map.getZoom() : 17;

    var offset =
        z >= 18 ? 0.00045 :
        z >= 17 ? 0.00070 :
                  0.00100;

    if (typeof _lastCamBrg === 'number') {
        var d = heading - _lastCamBrg;
        d = ((d + 540) % 360) - 180; // normalize to [-180..180]

        if (Math.abs(d) < 1.5) {
            heading = _lastCamBrg;
        }
    }
    var rad = heading * Math.PI / 180;

    var camLat = _camLat + Math.cos(rad) * offset;
    var camLng = _camLng + Math.sin(rad) * offset;

    map.setCenter({ lat: camLat, lng: camLng });

    if (!_isRotating && !_userInteracting) {
        try { map.setHeading(heading); } catch (e) { console.warn('map.setHeading failed', e); }
    }
    try { map.setTilt(45); } catch (e) { console.warn('map.setTilt failed', e); }
}
/** Backend / _driverRouteCoords: [[lng, lat], ...] -> path for google.maps.Polyline */
function pathLatLngFromLngLatPairs(coordsLL) {
    var path = [];
    for (var i = 0; i < (coordsLL || []).length; i++) {
        var p = coordsLL[i];
        if (!p || p.length < 2) continue;
        var lng = Number(p[0]);
        var lat = Number(p[1]);
        if (isNaN(lat) || isNaN(lng) || !isValidCoord(lat, lng)) continue;
        path.push({ lat: lat, lng: lng });
    }
    return path;
}
function setMainRoutePolylineFromDriverCoords() {
    if (!_driverRouteCoords || _driverRouteCoords.length < 2) return;

    var anchorIdx = Math.max(0, _routeAnchorIdx);
    var currentHash = _routeHash + '_' + anchorIdx;
    if (_smoothedCoordsHash === currentHash) return;
    _smoothedCoordsHash = currentHash;

    // Passed segment: origin → anchor (grey)
    var passed = _driverRouteCoords.slice(0, anchorIdx + 1);
    // Remaining segment: anchor → destination (yellow/active)
    var remaining = _driverRouteCoords.slice(anchorIdx);
    if (remaining.length < 2) remaining = _driverRouteCoords;

    // Draw remaining route (active - yellow)
    var activePath = pathLatLngFromLngLatPairs(remaining);
    if (activePath.length) setGoogleRoutePolyline(activePath);

    // Draw passed route (inactive - grey), if separate polyline exists
    if (typeof setPassedRoutePolyline === 'function' && passed.length >= 2) {
        var passedPath = pathLatLngFromLngLatPairs(passed);
        if (passedPath.length) setPassedRoutePolyline(passedPath);
    }
}
function smoothCoords(coords, factor) {
    var out = [];
    for (var i = 0; i < coords.length - 1; i++) {
        var a = coords[i];
        var b = coords[i + 1];

        out.push(a);

        for (var t = 1; t <= factor; t++) {
            var ratio = t / (factor + 1);
            out.push([
                a[0] + (b[0] - a[0]) * ratio,
                a[1] + (b[1] - a[1]) * ratio
            ]);
        }
    }
    out.push(coords[coords.length - 1]);
    return out;
}
function setPassedRoutePolyline(path) {
    if (!map || !_mapsJsReady() || !path || !path.length) return;
    if (!_gPassedPolyline) {
        _gPassedPolyline = new google.maps.Polyline({
            path: path,
            map: map,
            geodesic: false,
            strokeColor: '#AAAAAA',
            strokeWeight: 4,
            strokeOpacity: 0.5,
            zIndex: 0,
            lineJoin: 'round',
            lineCap: 'round'
        });
    } else {
        _gPassedPolyline.setPath(path);
        _gPassedPolyline.setMap(map);
    }
}
function setGoogleRoutePolyline(path) {
    if (!map || !_mapsJsReady() || !path || !path.length) return;
    if (!_gRoutePolyline) {
        _gRouteShadow = new google.maps.Polyline({
            path: path,
            map: map,
            strokeColor: '#C9A000',
            strokeOpacity: 0.85,
            strokeWeight: 12,
            geodesic: false,
            zIndex: 1,
            lineJoin: 'round',
            lineCap: 'round'
        });
        _gRoutePolyline = new google.maps.Polyline({
            path: path,
            map: map,
            geodesic: false,
            strokeColor: '#FFD400',
            strokeWeight: 7,
            strokeOpacity: 1,
            zIndex: 2,
            lineJoin: 'round',
            lineCap: 'round'
        });
    } else {
        if (_gRouteShadow) {
            _gRouteShadow.setPath(path);
            _gRouteShadow.setMap(map);
        }
        _gRoutePolyline.setPath(path);
        _gRoutePolyline.setMap(map);
        // Hide passed polyline when new route is drawn
        if (_gPassedPolyline) {
            _gPassedPolyline.setMap(null);
            _gPassedPolyline = null;
        }
    }
}
function setGoogleRouteABPolyline(path) {
    if (!map || !_mapsJsReady() || !path || !path.length) return;
    if (!_gRouteAbPolyline) {
        _gRouteAbPolyline = new google.maps.Polyline({
            path: path,
            map: map,
            geodesic: true,
            strokeColor: '#276EF1',
            strokeWeight: 4,
            strokeOpacity: 0.9,
            zIndex: 40
        });
    } else {
        _gRouteAbPolyline.setPath(path);
        _gRouteAbPolyline.setMap(map);
    }
}
function createHtmlBottomPinMarker(map, lng, lat, htmlInner) {
    var div = document.createElement('div');
    div.className = 'dest-wrap';
    div.innerHTML = htmlInner;
    var lat_ = lat, lng_ = lng;
    var overlay = new google.maps.OverlayView();
    overlay.onAdd = function() {
        var panes = this.getPanes();
        if (panes && panes.overlayMouseTarget) {
            panes.overlayMouseTarget.appendChild(div);
            div.style.position = 'absolute';
        }
    };
    overlay.draw = function() {
        var proj = this.getProjection();
        if (!proj || !div.parentNode) return;
        var p = proj.fromLatLngToDivPixel(new google.maps.LatLng(lat_, lng_));
        if (!p) return;
        div.style.left = p.x + 'px';
        div.style.top = (p.y - 48) + 'px';
        div.style.marginLeft = '-18px';
    };
    overlay.onRemove = function() {
        if (div.parentNode) div.parentNode.removeChild(div);
    };
    overlay.setMap(map);
    return {
        setLngLat: function(xy) {
            lng_ = xy[0];
            lat_ = xy[1];
            overlay.draw();
        },
        getLngLat: function() { return { lat: lat_, lng: lng_ }; },
        _overlay: overlay
    };
}
function createDriverMarkerView(map, lat, lng) {
    var wrap = document.createElement('div');
    wrap.className = 'dm-wrap';
    var circle = document.createElement('div');
    circle.className = 'dm-circle';
    var svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', '0 0 32 20');
    svg.setAttribute('class', 'dm-arrow');
    svg.innerHTML = '<path d="M16 1 L3 19 L16 14 L29 19 Z"/>';
    arrowEl = svg;
    circle.appendChild(svg);
    wrap.appendChild(circle);
    var lat_ = lat, lng_ = lng;
    var overlay = new google.maps.OverlayView();
    overlay.onAdd = function() {
        var panes = this.getPanes();
        if (panes && panes.overlayMouseTarget) {
            panes.overlayMouseTarget.appendChild(wrap);
            wrap.style.position = 'absolute';
            wrap.style.pointerEvents = 'none';
            wrap.style.width = '48px';
            wrap.style.height = '48px';
            wrap.style.marginLeft = '-24px';
            wrap.style.marginTop = '-24px';
            circle.style.transform = 'perspective(120px) rotateX(25deg)';
            circle.style.transformOrigin = 'center bottom';
            circle.style.filter = 'drop-shadow(0px 4px 6px rgba(0,0,0,0.4))';
        }
    };
    overlay.draw = function() {
        var projection = this.getProjection();
        if (!projection || !wrap.parentNode) return;
        var p = projection.fromLatLngToDivPixel(new google.maps.LatLng(lat_, lng_));
        if (!p) return;
        wrap.style.left = p.x + 'px';
        wrap.style.top = p.y + 'px';
    };
    overlay.onRemove = function() {
        if (wrap.parentNode) wrap.parentNode.removeChild(wrap);
    };
    overlay.setMap(map);
    return {
        setLngLat: function(arr) {
            lng_ = arr[0];
            lat_ = arr[1];
            overlay.draw();
        },
        getLngLat: function() { return { lat: lat_, lng: lng_ }; },
        _overlay: overlay
    };
}
function addDriverMarker(lat, lon) {
    if (driverMarker || !map) return;
    driverMarker = createDriverMarkerView(map, lat, lon);
}

function _temporarilyDisableFollow(ms) {
    _camBlockUntil = Date.now() + (ms || 5000);
}
function recenter() {
    _camBlockUntil = Date.now() + 380;
    if (dLat != null && dLng != null && map) {
        var zoom = speedToZoom(spd);
        var pitch = 60;
        var mpp = 156543 * Math.cos(dLat * Math.PI / 180) / Math.pow(2, zoom);
        var fwd = window.innerHeight * 0.15 * mpp / Math.cos(pitch * Math.PI / 180);
        var cc = getOffsetCenter(dLat, dLng, displayBearing, fwd);
        mapEaseToCamera({
            center: [cc[1], cc[0]],
            bearing: displayBearing,
            pitch: pitch,
            duration: 350
        });
    } else if (lastDriverLocation && map) {
        mapEaseToCamera({
            center: [lastDriverLocation.lon, lastDriverLocation.lat],
            bearing: displayBearing,
            pitch: 60,
            duration: 350
        });
    }
}
function zoomIn() {
    if (!map || !_mapsJsReady()) return;
    _temporarilyDisableFollow(3000);
    map.setZoom((map.getZoom() || 17) + 1);
}
function zoomOut() {
    if (!map || !_mapsJsReady()) return;
    _temporarilyDisableFollow(3000);
    map.setZoom(Math.max(10, (map.getZoom() || 17) - 1));
}
function renderLoop() {
    requestAnimationFrame(function(t) {
        var lt = renderLoop.lt;
        var dt = lt ? Math.min((t - lt) / 1000, 0.1) : 0.016;
        renderLoop.lt = t;

        var _nowMs = Date.now();

        // predictPosition ?????????????????????????????????????????????????????????
        // _drScale: smoothly activates dead reckoning between 2?? km/h.
        // Eliminates the flicker that a hard spd>2 threshold causes at low speed.
        // Formula: 0 when spd??, ramps linearly to 1 at spd=5, capped at 1.
        var _drScale = Math.min(Math.max((spd - 2) / 3, 0), 1);
        if (_gpsAnchorLat !== null && _drScale > 0) {
            var _drSec = Math.min((_nowMs - _gpsAnchorMs) / 1000, 2.5);
            var _aheadSec = 0;
            if (spd > 5) {
                _aheadSec = PREDICT_AHEAD_MIN_S + (PREDICT_AHEAD_MAX_S - PREDICT_AHEAD_MIN_S) *
                    Math.min((spd - 5) / 30, 1);
            }
            var _drSecPred = Math.min(_drSec + _aheadSec, 2.9);
            var _drDist = (spd / 3.6) * _drSecPred * _drScale; // meters to extrapolate
            // Route-based prediction: follows road geometry through curves.
            // Falls back to spherical-bearing projection if no route loaded.
            var _rp = advanceAlongRoute(_gpsAnchorLat, _gpsAnchorLng, _routeAnchorIdx, _drDist);
            if (_rp !== null) {
                _predLat = _rp[0];
                _predLng = _rp[1];
            } else {
                // Spherical projection along displayBearing ??correct for short arcs.
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
        // Snap predicted position onto route: throttled ~10 FPS (expensive Turf call).
        if (_nowMs - _lastPredSnapUpdate > 100) {
            if (typeof turf !== 'undefined' && _driverRouteLine && _driverRouteLine.geometry && _predLat !== null) {
                try {
                    var _predSnap = turf.nearestPointOnLine(_driverRouteLine, turf.point([_predLng, _predLat]));
                    if (_predSnap && _predSnap.geometry && _predSnap.geometry.coordinates) {
                        _predLat = _predSnap.geometry.coordinates[1];
                        _predLng = _predSnap.geometry.coordinates[0];
                    }
                } catch (_) {}
            }
            _lastPredSnapUpdate = _nowMs;
        }

        if (_predLat !== null && _predLng !== null) {
            if (_lastStableLat === null) {
                _lastStableLat = _predLat;
                _lastStableLng = _predLng;
            } else {
                var dist = haversineM(_predLat, _predLng, _lastStableLat, _lastStableLng);

                if (spd < 2 && dist < 4) {
                    _predLat = _lastStableLat;
                    _predLng = _lastStableLng;
                } else {
                    _lastStableLat = _predLat;
                    _lastStableLng = _predLng;
                }
            }
        }
        // updatePosition ?????????????????????????????????????????????????????????
        // ?_pos = 0.50s when parked: heavily damps GPS noise, prevents jitter.
        // ?_pos = 0.12s when moving: fast settling (~360ms), GPS jumps absorbed.
        // 慣 = 1 - exp(-dt / ?)
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

        if (_driverRouteLine && _driverRouteCoords && _driverRouteCoords.length > 1 && typeof turf !== 'undefined') {
            if (_nowMs - _lastRouteSnapUpdate2 > 100) {
                _lastRouteSnapUpdate2 = _nowMs;
                var rawLat = dLat;
                var rawLng = dLng;

                var distM = 0;

                try {
                    var pt = turf.point([rawLng, rawLat]);
                    var snap = turf.nearestPointOnLine(_driverRouteLine, pt, { units: 'kilometers' });

                    if (snap && snap.geometry && snap.geometry.coordinates) {
                        if (snap.properties && typeof snap.properties.dist === 'number') {
                            distM = snap.properties.dist * 1000;
                        } else {
                            distM = 9999; // force RAW GPS fallback
                        }

                        // Snap hysteresis: avoid snap/raw flapping near threshold.
                        if (!isSnapped && distM < 60) {
                            isSnapped = true;
                        }
                        if (isSnapped  && distM > 80) {
                            isSnapped = false;
                            // Off-route: use raw GPS, do not snap to wrong road
                            dLat = tLat;
                            dLng = tLng;
                        }

                        if (isSnapped) {
                            dLat += (snap.geometry.coordinates[1] - dLat) * 0.5;
                            dLng += (snap.geometry.coordinates[0] - dLng) * 0.5;

                            if (snap.properties && snap.properties.index != null) {
                                var maxIdx = _driverRouteCoords.length > 1 ? _driverRouteCoords.length - 2 : 0;
                                var newIdx = Math.min(snap.properties.index, maxIdx);

                                if (typeof _routeAnchorIdx !== 'number' || isNaN(_routeAnchorIdx)) {
                                    _routeAnchorIdx = newIdx;
                                } else {
                                    var diff = newIdx - _routeAnchorIdx;

                                    if (diff >= 0 && diff <= 15) { // FIXED: BUG#5
                                        _routeAnchorIdx = newIdx;
                                    }
                                }
                            }
                        } else if (!isSnapped) {
                            // Already handled by snap exit block above — do not overwrite
                        }
                    }
                } catch (_) {}
            }
        }

        // updateBearing ?????????????????????????????????????????????????????????
        // Route-based heading (segment bearing); GPS/lastHeading only as fallback.
        var _routeBearingApplied = false;
        if (typeof turf !== 'undefined' &&
            _driverRouteLine && _driverRouteLine.geometry &&
            _driverRouteCoords &&
            _driverRouteCoords.length > 1 &&
            typeof _routeAnchorIdx === 'number' &&
            !isNaN(_routeAnchorIdx)) {

            var _i = Math.max(0, Math.min(_routeAnchorIdx, _driverRouteCoords.length - 2));
            var _curr = _driverRouteCoords[_i];
            var _next = _driverRouteCoords[_i + 1];

            if (_curr && _next) {
                var _routeBrg = turf.bearing(turf.point(_curr), turf.point(_next));
                brg = (_routeBrg + 360) % 360;
                _routeBearingApplied = true;
            }
        }
        if (!_routeBearingApplied && lastHeading != null && !isNaN(lastHeading)) {
            brg = (Number(lastHeading) + 360) % 360;
        }

        // ?_brg = 0.80 - 0.65 횞 min(spd/30, 1)
        // ? at  0 km/h: 0.80s ??absorbs GPS bearing noise when nearly stopped.
        // ? at 30 km/h: 0.15s ??tracks highway bends without lag.
        // ? at 60 km/h: 0.15s ??capped; faster would overshoot sharp turns.
        if (!useManualBearing) targetBearing = northUpMode ? 0 : brg;
        var _tauBrg = 0.80 - 0.65 * Math.min(spd / 30, 1);
        var _brgDecay = Math.exp(-dt / _tauBrg);
        var _brgShortcut = ((targetBearing - displayBearing + 540) % 360) - 180;
        displayBearing = (displayBearing + _brgShortcut * (1 - _brgDecay) + 360) % 360;

        // Arrow heading: fast when actually moving (even if GPS spd is noisy).
        var _moveMHead = (dLat != null && dLng != null && _lastDbgLat != null && _lastDbgLng != null)
            ? haversineM(dLat, dLng, _lastDbgLat, _lastDbgLng) : 0;
        var _isMovingHead = (spd >= 3) || (_moveMHead > 1);
        var _tauHead = _isMovingHead ? 0.08 : 0.25;
        var _headDecay = Math.exp(-dt / _tauHead);
        var _hdShortcut = ((brg - displayHeading + 540) % 360) - 180;
        displayHeading = (displayHeading + _hdShortcut * (1 - _headDecay) + 360) % 360;
        _lastDbgLat = dLat;
        _lastDbgLng = dLng;

        // _displayArrowBrg: displayBearing ni strelka uchun alohida smooth kuzatadi.
        // tau=0.06s — displayBearing (tau ~0.15-0.80s) dan tezroq,
        // shuning uchun kamera aylanayotganda strelka unga yopishib qoladi.
        if (_displayArrowBrg === null) _displayArrowBrg = displayBearing;
        var _arrowBrgShortcut = ((displayBearing - _displayArrowBrg + 540) % 360) - 180;
        _displayArrowBrg = (_displayArrowBrg + _arrowBrgShortcut * (1 - Math.exp(-dt / 0.06)) + 360) % 360;

        if (driverMarker && dLat !== null && dLng !== null) {
            if (_dispLat === null || _dispLng === null) {
                _dispLat = dLat;
                _dispLng = dLng;
            }
            _dispLat += (dLat - _dispLat) * 0.2;
            _dispLng += (dLng - _dispLng) * 0.2;

        /* Arrival magnetism: smoothly pull rendered position to destination in final 40m.
           Visual-only: does NOT modify dLat/dLng or routing logic. */
        if ((appState === 'arriving' || appState === 'ready') &&
            typeof ORDER_DATA !== 'undefined' &&
            ORDER_DATA &&
            ORDER_DATA.destination_latitude != null &&
            ORDER_DATA.destination_longitude != null &&
            _dispLat !== null && _dispLng !== null &&
            dLat !== null && dLng !== null) {
            try {
                var _arrDstLat = ORDER_DATA.destination_latitude;
                var _arrDstLng = ORDER_DATA.destination_longitude;

                // distance based on logic position (dLat/dLng), not display
                var _arrDist = haversineM(dLat, dLng, _arrDstLat, _arrDstLng);

                // If last segment is unnamed short road, ignore final 80m snap
                var _effectiveArrivalZone = _destOffsetActive ? 0 : 40;

                if (_arrDist < _effectiveArrivalZone && _arrDist > 0) {
                    // blend factor: 0 at zone boundary to 1 at 0m
                    var _arrBlend = (_effectiveArrivalZone - _arrDist) / _effectiveArrivalZone;

                    // gentle pull (no teleport)
                    var _alpha = _arrBlend * 0.25; // max 0.25 per tick

                    _dispLat += (_arrDstLat - _dispLat) * _alpha;
                    _dispLng += (_arrDstLng - _dispLng) * _alpha;
                }
            } catch (e) {}
        }

            // UI jitter filter (meter-based, Google Maps safe)
            var _renderLat = _dispLat;
            var _renderLng = _dispLng;

            if (_lastRenderLat != null && _lastRenderLng != null) {
                var _zoom = map && map.getZoom ? map.getZoom() : 17;

                // meters per pixel (approx)
                var _mpp = (156543.03 * Math.cos(_dispLat * Math.PI / 180)) / Math.pow(2, _zoom);

                // 3px equivalent in meters
                var _threshM = _mpp * 3;

                var _moveM = haversineM(_dispLat, _dispLng, _lastRenderLat, _lastRenderLng);

                if (_moveM < _threshM) {
                    _renderLat = _lastRenderLat;
                    _renderLng = _lastRenderLng;
                }
            }

            _lastRenderLat = _renderLat;
            _lastRenderLng = _renderLng;

            driverMarker.setLngLat([_renderLng, _renderLat]);

            var _targetDeg = (displayHeading - _displayArrowBrg + 720) % 360;
            if (_dispArrowDeg === null) {
                _dispArrowDeg = _targetDeg;
            }
            var delta = ((_targetDeg - _dispArrowDeg + 540) % 360) - 180;
            _dispArrowDeg += delta * 0.2;
            if (arrowEl) {
                arrowEl.style.transform = 'rotate(' + _dispArrowDeg + 'deg)';
            }
            // Adaptive intervals: slower when parked (stability), faster when moving (responsiveness).
            var _navInterval  = spd < 5 ? 150 : 80;
            if (_nowMs - _lastNavUpdate > _navInterval) {
                setTurnAndDistFromDriver({ lat: dLat, lng: dLng });
                if ((appState === 'arriving' || appState === 'ready') && routeCoordinates.length >= 2) {
                    var remainingKm = calculateRemainingDistance(dLat, dLng);
                    remainingKm = Number(remainingKm.toFixed(2));
                    if (lastBottomDistance !== null) {
                        remainingKm = Math.min(remainingKm, lastBottomDistance);
                    }
                    lastBottomDistance = remainingKm;
                    var remainingMin = calculateRemainingTime(remainingKm);
                    if (_nowMs - lastBottomUpdateTs > 300) {
                        updateBottomPanel(remainingKm, remainingMin);
                        lastBottomUpdateTs = _nowMs;
                    }
                }
                // DOM guard: skip repaint when turn index and distance haven't meaningfully changed.
                if (turnI !== _lastTurnI || _lastDist === null || Math.abs(distKm - _lastDist) > 0.01) {
                    updateNavUI();
                    _lastTurnI = turnI;
                    _lastDist  = distKm;
                }
                _lastNavUpdate = _nowMs;
            }
        }

        if (_userInteracting) {
            if (Date.now() - _lastUserInteraction > 2500) {
                _userInteracting = false;
                _isRotating = false;
            }
        }

        // updateCamera ??????????????????????????????????????????????????????????
        // Uses _camLat/Lng (camera-smoothed position) ??not raw dLat/dLng ??
        // to avoid float jitter reaching the GPU.
        // _screenRatio: 0.15 at rest ??0.25 at 80 km/h.
        // Larger ratio = vehicle lower on screen = more road visible ahead.
        // GPU redraw suppressed when position and bearing are sub-pixel stable.
        if (dLat !== null) {
            // Smooth zoom via EMA (alpha=0.02/frame) to prevent flicker at speed-band boundaries.
            var _zoomTarget = speedToZoom(spd);
            if (_stableZoom === null) { _stableZoom = _zoomTarget; }
            else { _stableZoom += (_zoomTarget - _stableZoom) * 0.02; }
            var _zoom = _stableZoom;
            var _brgDelta = Math.abs(((displayHeading - _lastCamBrg + 540) % 360) - 180);
            var _moveDist = (_lastCamLat != null && _lastCamLng != null)
                ? haversineM(dLat, dLng, _lastCamLat, _lastCamLng) : 999;
            var _moved = _moveDist > 1;
            var _zoomDelta = Math.abs(_zoom - _lastCamZoom);
            var _timeForced = (_nowMs - _lastCamUpdate > 500);
            if ((_nowMs - _lastCamUpdate > 130) &&
                (_moved || _brgDelta > 2 || _zoomDelta > 0.1 || _timeForced)) {
                if (Date.now() >= _camBlockUntil) {
                    var currentHeading = displayHeading;
                    if (!_userInteracting) {
                        var _camFeedLat = (_dispLat !== null) ? _dispLat : dLat;
                        var _camFeedLng = (_dispLng !== null) ? _dispLng : dLng;
                        updateCamera(_camFeedLat, _camFeedLng, currentHeading);
                    }
                    _lastCamBrg = currentHeading;

                    _lastCamLat = dLat;
                    _lastCamLng = dLng;
                    _lastCamUpdate = _nowMs;
                } else {
                    // Camera blocked by recent user interaction (recenter/zoom).
                }
            }
        }

        renderLoop();
    });
}
function updateNavUI() {
    var distM = formatDistance(distKm * 1000);
    var inst = routeInstructions[turnI] || routeInstructions[0];
    var street = inst && inst.text ? inst.text : "Mijozga yol";
    var turnType = inst && inst.type != null ? inst.type : -1;
    var tkey = 'straight';
    if (routeInstructions.length && (turnI >= routeInstructions.length - 1)) {
        tkey = 'arrive';
    } else if (turnType >= 6 && turnType <= 8 || turnType === -1) {
        tkey = 'left';
    } else if (turnType >= 2 && turnType <= 4 || turnType === 1) {
        if (turnType === 1 && street.indexOf('Chapga') !== -1) tkey = 'left';
        else if (turnType === 1 && street.indexOf("O'ngga") !== -1) tkey = 'right';
        else if (turnType === 1) tkey = 'straight';
        else tkey = 'right';
    } else if (turnType === 0) {
        tkey = 'straight';
    }
    var svg = document.getElementById('turn-svg');
    if (svg) svg.innerHTML = TSVG[tkey] || TSVG.straight;
    var topDist = document.getElementById('top-dist');
    var topRoad = document.getElementById('top-road');
    if (topDist) {
        topDist.textContent = distM;
        topDist.style.fontSize = "1.15rem";
        topDist.style.fontWeight = "600";
    }
    if (topRoad) {
        topRoad.textContent = street;
        topRoad.style.fontWeight = "bold";
        topRoad.style.fontSize = "1.05rem";
    }
    var avg = Math.max(spd, 8);
    var mins = Math.round((distKm / avg) * 60);
    var eta = new Date();
    eta.setMinutes(eta.getMinutes() + mins);
    var et = document.getElementById('eta-t');
    var ed = document.getElementById('eta-d');
    if (et) et.textContent = eta.getHours().toString().padStart(2,'0') + ':' + eta.getMinutes().toString().padStart(2,'0');
    if (ed) ed.textContent = formatDistance(distKm * 1000);
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
        // Reset match pipeline buffers for new trip
        _gpsMatchBuffer.length = 0;
        _matchCallCount = 0;
        _routeRedrawCount = 0;
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

function activateTaximeterUI() {
    document.body.classList.add('taximeter-mode');

    var arriving = document.getElementById('arrivingPanel');
    var taximeter = document.getElementById('taximeterScreen');
    var mapEl = document.getElementById('map');

    if (arriving) arriving.style.display = 'none';
    if (taximeter) taximeter.classList.add('active');
    if (mapEl) mapEl.classList.add('minimized');

    var topBar = document.querySelector('.top-bar');
    if (topBar) topBar.classList.add('hidden');
    var navEl = document.querySelector('.nav');
    if (navEl) navEl.classList.add('hidden');
    var compass = document.querySelector('.compass');
    if (compass) compass.classList.add('hidden');

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

    if (!intervals.timer) {
        intervals.timer = setInterval(updateTimer, 1000);
    }
    if (appState === 'trip') {
        startTripMeterPolling();
    }
}

async function init() {
    const savedTrip = localStorage.getItem('trip_active_order_id');
    if (!navigator.onLine && savedTrip) {
        appState = 'trip';
        activateTaximeterUI();
        enableWakeLock(); // may fail silently, OK
    } else {
        await fetchClientLocation();
    }
    if (!ORDER_DATA && !(savedTrip && !navigator.onLine)) return;

    /* Order already completed or cancelled */
    if (ORDER_DATA.status === 'completed' || ORDER_DATA.status === 'cancelled') {
        showOrderCompleted(ORDER_DATA.status);
        return;
    }

    /* Trip already started */
    if (ORDER_DATA.status === 'in_progress') {
        appState = 'trip';
        _needsTripRouteRestore = true;
        activateTaximeterUI();
        enableWakeLock(); // may fail silently, OK

        try {
            var oid = (ORDER_DATA && ORDER_DATA.id != null) ? ORDER_DATA.id : ORDER_ID_CURRENT;
            if (!oid) throw new Error('order_id missing for trip-meter');
            const res = await fetch(
                API_BASE_URL + '/api/webapp/order/' + oid + '/trip-meter?v=' + Date.now(),
                { headers: webappHeaders() }
            );
            if (!res.ok) throw new Error('trip-meter http ' + res.status);
            const data = await res.json();
            if (data && data.active) {
                tripData.distance = data.distance_km || 0;
                if (!tripData.isWaiting) {
                    tripData.waitingTime = data.waiting_seconds || 0;
                }
                tripData.isWaiting = !!data.is_waiting;
                tripData.surge = data.surge_multiplier != null && data.surge_multiplier !== undefined ? Number(data.surge_multiplier) : (tripData.surge || 1);
                if (data.estimated_fare != null) tripData.serverFare = data.estimated_fare;
                if (data.elapsed_seconds != null && !isNaN(Number(data.elapsed_seconds))) {
                    tripData.elapsedSeconds = Number(data.elapsed_seconds) || 0;
                }
                updateTaximeter();
            }
        } catch (e) {
            console.warn('Trip restore failed', e);
        }
    }

    initMap();
    startDriverTracking();
    updateSyncUI();
    flushPendingTrips();
}

function initMap() {
    if (!ORDER_DATA || !isValidCoord(ORDER_DATA.pickup_latitude, ORDER_DATA.pickup_longitude)) {
        var leEarly = document.getElementById('loading');
        if (leEarly) leEarly.classList.add('hidden');
        showError("Buyurtma joylashuvi noto'g'ri.");
        return;
    }
    var lat = ORDER_DATA.pickup_latitude;
    var lon = ORDER_DATA.pickup_longitude;

    if (!_mapsJsReady()) {
        var leG = document.getElementById('loading');
        if (leG) leG.classList.add('hidden');
        showError("Google Maps yuklanmadi. GOOGLE_MAPS_JS_KEY sozlang.");
        return;
    }
    try {
        initGoogleMap(lat, lon);
    } catch (e) {
        var leMap = document.getElementById('loading');
        if (leMap) leMap.classList.add('hidden');
        showError("Xarita boshlanmadi.");
        return;
    }

    // IMPORTANT: Do not use map 'dragstart' for follow blocking during navigation.
    // On some devices it can fire during programmatic camera updates and permanently block the camera.
    // We only block follow on direct user touch/pointer interaction (see setupMapGestures()).

    google.maps.event.addListenerOnce(map, 'idle', function() {
        try {
            clientMarker = createHtmlBottomPinMarker(
                map, lon, lat,
                '<div class="dest-pin"><span id="destPinLabel">MANZIL</span></div>'
            );
            setInterval(refreshDistanceDisplay, 5000);
            var destLat = ORDER_DATA.destination_latitude;
            var destLon = ORDER_DATA.destination_longitude;
            if (destLat != null && destLon != null && isValidCoord(destLat, destLon) && (Math.abs(destLat - lat) > 0.0001 || Math.abs(destLon - lon) > 0.0001)) {
                destMarker = createHtmlBottomPinMarker(
                    map, destLon, destLat,
                    '<div class="dest-pin"><span>B</span></div>'
                );
                drawRouteAB({ lat: lat, lng: lon }, { lat: destLat, lng: destLon });
            }
            var leOk = document.getElementById('loading');
            if (leOk) leOk.classList.add('hidden');
            if (!renderLoopRunning) { renderLoopRunning = true; renderLoop(); }
            setupMapGestures();
        } catch (e) {
            var leCatch = document.getElementById('loading');
            if (leCatch) leCatch.classList.add('hidden');
            showError("Xarita yuklanmadi. Sahifani yangilang.");
        }
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
            if (northUpMode) {
                targetBearing = 0;
                compassBtn.style.background = '#1A73E8';
                if (compassBtn.querySelector('svg')) compassBtn.querySelector('svg').style.filter = 'invert(1)';
            } else {
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
    if (routeCoordinates.length >= 2 && typeof _routeAnchorIdx === 'number' && !isNaN(_routeAnchorIdx)) {
        var dLatR = lastDriverLocation ? lastDriverLocation.lat : null;
        var dLngR = lastDriverLocation ? lastDriverLocation.lon : null;
        var rk = calculateRemainingDistance(dLatR, dLngR);
        rk = Number(rk.toFixed(2));
        if (lastBottomDistance !== null) {
            rk = Math.min(rk, lastBottomDistance);
        }
        lastBottomDistance = rk;
        var rm = calculateRemainingTime(rk);
        updateBottomPanel(rk, rm);
        lastBottomUpdateTs = Date.now();
        return;
    }
    var d = 0;
    if (lastDriverLocation && ORDER_DATA.pickup_latitude != null && ORDER_DATA.pickup_longitude != null) {
        d = haversineM(lastDriverLocation.lat, lastDriverLocation.lon, ORDER_DATA.pickup_latitude, ORDER_DATA.pickup_longitude) / 1000;
    }
    if (routeRoadDistanceKm != null && routeRoadDistanceKm > 0) d = routeRoadDistanceKm;
    if (d > MAX_DISTANCE_KM || d < 0 || isNaN(d)) { distEl.textContent = '0.00'; timeEl.textContent = '??'; return; }
    distEl.textContent = d.toFixed(2);
    timeEl.textContent = '~' + Math.max(1, Math.round(d / AVG_SPEED_KMH * 60));
}
function fitBoundsToMarkers() {
    if (!map || !_mapsJsReady()) return;
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
    var bounds = new google.maps.LatLngBounds();
    bounds.extend(new google.maps.LatLng(minLat, minLng));
    bounds.extend(new google.maps.LatLng(maxLat, maxLng));
    map.fitBounds(bounds, 100);
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
    return fetch(API_BASE_URL + '/api/webapp/update_driver_location?v=' + Date.now(), {
        method: 'POST',
        headers: webappHeaders(),
        body: JSON.stringify(body)
    })
        .then(function(r) {
            if (appState === 'trip' && r && r.ok) fetchTripMeterSnapshot();
        })
        .catch(function() {});
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
                if (intervals.position != null) { // FIXED: BUG#6
                    clearInterval(intervals.position);
                    intervals.position = null;
                }
                _startBrowserGPS(opts);
            });
            return;
        } catch (e) {
            if (intervals.position != null) { // FIXED: BUG#6
                clearInterval(intervals.position);
                intervals.position = null;
            }
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
    if (el) el.textContent = '??';
    el = document.getElementById('timeToClient');
    if (el) el.textContent = '??';
    document.getElementById('loading').classList.add('hidden');
    if (map && ORDER_DATA && isValidCoord(ORDER_DATA.pickup_latitude, ORDER_DATA.pickup_longitude)) {
        mapEaseToCamera({
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
    if (el) el.textContent = '??';
    el = document.getElementById('timeToClient');
    if (el) el.textContent = '??';
    document.getElementById('loading').classList.add('hidden');
    showGpsModal();
}

function setTurnAndDistFromDriver(driverPos) {
    if (!driverPos || !routeCoordinates.length || !routeInstructions.length) return;
    var toLatLng = function(c) { return c && (c.lat != null) ? { lat: c.lat, lng: c.lng } : { lat: c[0], lng: c[1] }; };
    var progressIdx = 0;
    if (typeof _routeAnchorIdx === 'number' && !isNaN(_routeAnchorIdx)) {
        progressIdx = Math.max(0, Math.min(_routeAnchorIdx, routeCoordinates.length - 1));
    }
    // Advance pointer only forward: skip maneuvers whose intersection is at or behind progress.
    while (_currentInstructionIndex < routeInstructions.length) {
        var _instScan = routeInstructions[_currentInstructionIndex];
        var _idxScan = _instScan.index != null ? _instScan.index : (_instScan.intersection_index != null ? _instScan.intersection_index : _currentInstructionIndex);
        if (_idxScan > progressIdx) break;
        _currentInstructionIndex++;
    }
    if (_currentInstructionIndex >= routeInstructions.length) {
        _currentInstructionIndex = routeInstructions.length - 1;
    }
    var nextInst = routeInstructions[_currentInstructionIndex];
    var instIdx = nextInst.index != null ? nextInst.index : (nextInst.intersection_index != null ? nextInst.intersection_index : routeCoordinates.length - 1);
    turnI = _currentInstructionIndex;
    var turnCoord = routeCoordinates[Math.min(instIdx, routeCoordinates.length - 1)];
    var t = toLatLng(turnCoord);
    distKm = turnCoord ? haversineM(driverPos.lat, driverPos.lng, t.lat, t.lng) / 1000 : 0;
}
function _pushGpsBuffer(lat, lng) {
    _gpsMatchBuffer.push({ lat, lng, ts: Math.floor(Date.now() / 1000) });
    if (_gpsMatchBuffer.length > _GPS_BUFFER_SIZE) _gpsMatchBuffer.shift();
}

async function _fetchMapMatch() {
    if (_matchInFlight) return;
    if (_gpsMatchBuffer.length < 3) return;
    if (!ORDER_DATA?.id) return;

    _matchInFlight = true;

    // Safe abort pattern — AbortSignal.timeout() not supported in Telegram WebView
    var _matchController = new AbortController();
    var _matchTimeout = setTimeout(function() {
        _matchController.abort();
    }, 4000);

    try {
        const payload = {
            coordinates: _gpsMatchBuffer.map(function(p) { return [p.lng, p.lat]; }),
            timestamps:  _gpsMatchBuffer.map(function(p) { return p.ts; }),
            radiuses:    _gpsMatchBuffer.map(function()  { return 35; })
        };

        const res = await fetch(
            API_BASE_URL + '/api/webapp/order/' + ORDER_DATA.id + '/map-match',
            {
                method: 'POST',
                headers: Object.assign({}, webappHeaders(), { 'Content-Type': 'application/json' }),
                body: JSON.stringify(payload),
                signal: _matchController.signal
            }
        );

        clearTimeout(_matchTimeout);

        if (!res.ok) return;
        const data = await res.json();

        if (
            data && data.matched &&
            data.matched.lat != null &&
            data.matched.lng != null &&
            tLat !== null && tLng !== null
        ) {
            // Soft EMA injection into global tLat/tLng
            // renderLoop reads these next frame — pipeline continues unchanged
            tLat = tLat + 0.35 * (data.matched.lat - tLat);
            tLng = tLng + 0.35 * (data.matched.lng - tLng);
        }

    } catch (e) {
        clearTimeout(_matchTimeout);
        // silent fallback — existing EMA pipeline continues unchanged
    } finally {
        _matchInFlight = false;
    }
}

function updateDriverMarker(lat, lng, heading) {
    try {
        if (!map || !ORDER_DATA) return;
        if (!isValidCoord(lat, lng)) return;
        // Cache GPS heading for rotation fallback when route bearing isn't available.
        if (heading != null && !isNaN(Number(heading))) {
            lastHeading = (Number(heading) + 360) % 360;
        }
        // Route not loaded yet AND marker already created ??queue and wait.
        // The first call (driverMarker is undefined/falsy) must fall through so
        // it can call addDriverMarker() and drawRoute(), which triggers directions fetch
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
        // Raw GPS only here — route snap lives in renderLoop (dLat/dLng / marker display).
        var sl = lat;
        var sa = lng;
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
        // /match pipeline
        _pushGpsBuffer(lat, lng);
        _matchCallCount++;
        if (_matchCallCount % 3 === 0) {
            _fetchMapMatch(); // fire-and-forget, intentionally not awaited
        }
        spd = speedKmh;
        // Velocity estimation with EMA smoothing at GPS rate.
        // Raw velocity = ?snapped / ?t_gps. One noisy GPS fix can spike 짹27 km/h
        // on the raw estimate; EMA filters this without staling the prediction.
        // 慣_vel: 0.4 at low speed (???s at 2s GPS rate) ??0.7 at 20+ km/h (???.5s).
        // Conversion: ? = -?t / ln(1-慣). 慣=0.4 @ ?t=2s ???=3.9s. 慣=0.7 ???=1.5s.
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
        // _routeAnchorIdx is advanced in renderLoop (post-smooth Turf snap).
        _gpsAnchorLat = sl;
        _gpsAnchorLng = sa;
        _gpsAnchorMs = now;
        updateProgressiveRoute(sa, sl);
        if (!driverMarker) {
            var _tangentInit = (typeof turf !== 'undefined' && _driverRouteLine)
                ? getRouteTangentBearing(sa, sl) : null;
            var _initBrg = _tangentInit !== null ? _tangentInit
                : ((_prevSnappedLat != null && _prevSnappedLng != null)
                    ? calcBearing(_prevSnappedLat, _prevSnappedLng, sl, sa) : brg);
            headingBuffer = [brg];
            displayHeading = _initBrg;
            displayBearing = _initBrg;
            targetBearing = _initBrg;
            addDriverMarker(sl, sa);
            dLat = sl;
            dLng = sa;
            mapEaseToCamera({ center: [sa, sl], zoom: 18, duration: 600 });
            var pickLat = ORDER_DATA.pickup_latitude;
            var pickLon = ORDER_DATA.pickup_longitude;
            if (pickLat != null && pickLon != null) drawRoute(driverPos, { lat: pickLat, lng: pickLon });
            // Trip restore: ensure destination route is drawn (same logic as handleStartTrip).
            if (_needsTripRouteRestore && appState === 'trip' &&
                ORDER_DATA.destination_latitude != null && ORDER_DATA.destination_longitude != null) {
                drawRoute(driverPos, { lat: ORDER_DATA.destination_latitude, lng: ORDER_DATA.destination_longitude });
                _needsTripRouteRestore = false;
            }
            document.getElementById('loading').classList.add('hidden');
        } else {
            var _brgPreBuf = brg;
            var _prevBufMean = headingBuffer.length ? circularMeanHeadings(headingBuffer) : _brgPreBuf;
            var _bufTurnDiff = Math.abs(((_brgPreBuf - _prevBufMean + 540) % 360) - 180);
                if (_bufTurnDiff > HEADING_BUFFER_RESET_DEG && speedKmh > 8) headingBuffer = [];
                headingBuffer.push(_brgPreBuf);
                if (headingBuffer.length > HEADING_BUFFER_MAX) headingBuffer.shift();
                // brg is owned by renderLoop (route-based single source)
        }
        if (!routeCoordinates.length) {
            if (ORDER_DATA.pickup_latitude != null && ORDER_DATA.pickup_longitude != null) {
                distKm = haversineM(driverPos.lat, driverPos.lng, ORDER_DATA.pickup_latitude, ORDER_DATA.pickup_longitude) / 1000;
            }
        }
        // Trip o'lchovi (taximeter) masofasi: faqat server /trip-meter dan (tripData.distance).
        // Mahalliy segment qo'shish olib tashlangan — aks holda client sum > Redis sum bo'lib,
        // keyingi poll display ni orqaga sakratardi (masalan 7 -> 3).
        if (appState === 'trip' && !tripData.isWaiting) {
            tripData.lastPosition = driverPos;
            maybeSyncToServer();
        }
        checkOffRoute(lat, lng, speedKmh);
    } catch (e) {}
}

function startSim() {
    if (simOn || !routeCoordinates.length) return;
    simOn = true;
    var lbl = document.getElementById('sim-lbl');
    if (lbl) lbl.textContent = '??';
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
    if (lbl) lbl.textContent = '??';
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
    simIdx++;
    // Nav UI driven by renderLoop; no duplicate call here.
}

function resetRouteProgress() {
    _lastProgressAnchorIdx = null;
    _currentInstructionIndex = 0;
    lastBottomDistance = null;
    lastBottomUpdateTs = 0;
}

function _clearRouteFetchCache() {
    _routeFetchCache = null;
}

function _saveRouteFetchCache(fromLat, fromLng, toLat, toLng) {
    if (!_driverRouteCoords || _driverRouteCoords.length < 2) return;
    _routeFetchCache = {
        oLat: fromLat,
        oLng: fromLng,
        dLat: toLat,
        dLng: toLng,
        roadKm: routeRoadDistanceKm,
        instr: routeInstructions.map(function(s) {
            return { text: s.text, type: s.type, index: s.index };
        }),
        coordsLonLat: _driverRouteCoords.map(function(c) { return [c[0], c[1]]; })
    };
}

function _tryReuseRouteFetchCache(fromLat, fromLng, toLat, toLng) {
    var c = _routeFetchCache;
    if (!c || !c.coordsLonLat || c.coordsLonLat.length < 2) return false;
    if (haversineM(c.oLat, c.oLng, fromLat, fromLng) >= ROUTE_CACHE_NEAR_M) return false;
    if (haversineM(c.dLat, c.dLng, toLat, toLng) >= ROUTE_CACHE_NEAR_M) return false;
    routeRoadDistanceKm = c.roadKm;
    routeInstructions = c.instr.map(function(s) {
        return { text: s.text, type: s.type, index: s.index };
    });
    _driverRouteCoords = c.coordsLonLat.map(function(p) { return [p[0], p[1]]; });
    routeCoordinates = _driverRouteCoords.map(function(pt) { return [pt[1], pt[0]]; });
    if (!routeInstructions.length) {
        routeInstructions = buildPolylineManeuvers(routeCoordinates);
    }
    _currentInstructionIndex = 0;
    return true;
}

/** Turf + map layer after routeCoordinates / _driverRouteCoords are set (API or cache). */
function _applyRouteGeometryToMap(fromLat, fromLng, toLat, toLng) {
    if (!routeCoordinates.length) {
        fallbackStraightLine(fromLat, fromLng, toLat, toLng);
        return;
    }
    if (typeof turf !== 'undefined' && _driverRouteCoords.length >= 2) {
        try { _driverRouteLine = turf.lineString(_driverRouteCoords); } catch (_) {}
        isSnapped = false;
        _routeAnchorIdx = 0;
    }
    _snapRouteLine = _driverRouteLine;
    if (typeof turf !== 'undefined' && _driverRouteLine && dLat !== null) {
        try {
            var snap = turf.nearestPointOnLine(
                _driverRouteLine,
                turf.point([dLng, dLat])
            );

            if (snap && snap.geometry && snap.geometry.coordinates) {

                var newLng = snap.geometry.coordinates[0];
                var newLat = snap.geometry.coordinates[1];

                tLat = newLat;
                tLng = newLng;

                dLat = newLat;
                dLng = newLng;

                _gpsAnchorLat = newLat;
                _gpsAnchorLng = newLng;
                _gpsAnchorMs = Date.now();

                _predLat = newLat;
                _predLng = newLng;

                _lastStableLat = newLat;
                _lastStableLng = newLng;

                headingBuffer = [];

                _lastProgressLat = newLat;
                _lastProgressLng = newLng;

            }
        } catch (_) {}
    }
    if (_pendingGps !== null) {
        var _pg = _pendingGps; _pendingGps = null;
        updateDriverMarker(_pg.lat, _pg.lng, _pg.heading);
    }
    // Redraw route only every 3 GPS updates
    _routeRedrawCount++;
    if (_routeRedrawCount % 3 === 0) {
        setMainRoutePolylineFromDriverCoords();
    }
    setTurnAndDistFromDriver({ lat: fromLat, lng: fromLng });
    updateNavUI();
}

function drawRoute(from, to, opts) {
    opts = opts || {};
    if (!map || !from || !to) return Promise.resolve(false);
    if (_routeInFlight && !opts?.fromReroute) return Promise.resolve(false);
    if (_rerouteInFlight && !opts.fromReroute) return Promise.resolve(false);
    const requestId = ++_routeRequestId;

    // from: L.LatLng yoki {lat, lng} bo?쁫ishi mumkin
    var fromLat = from.lat != null ? from.lat : from[0];
    var fromLng = from.lng != null ? from.lng : from[1];
    var toLat = to.lat != null ? to.lat : to[0];
    var toLng = to.lng != null ? to.lng : to[1];

    if (!isValidCoord(fromLat, fromLng) || !isValidCoord(toLat, toLng)) {
        return Promise.resolve(false);
    }

    var segM = haversineM(fromLat, fromLng, toLat, toLng);
    if (segM < ROUTE_SAME_ENDPOINT_M) {
        fallbackStraightLine(fromLat, fromLng, toLat, toLng);
        return Promise.resolve(true);
    }
    if (segM < ROUTE_MIN_API_SEGMENT_M) {
        fallbackStraightLine(fromLat, fromLng, toLat, toLng);
        return Promise.resolve(true);
    }

    var oid = getTripOrderIdForApi();
    if (!oid) {
        fallbackStraightLine(fromLat, fromLng, toLat, toLng);
        return Promise.resolve(true);
    }

    if (_tryReuseRouteFetchCache(fromLat, fromLng, toLat, toLng)) {
        resetRouteProgress();
        _applyRouteGeometryToMap(fromLat, fromLng, toLat, toLng);
        _lastRouteUpdateTs = Date.now();
        return Promise.resolve(true);
    }

    _routeInFlight = true;
    routeRoadDistanceKm = null;
    routeInstructions = [];
    routeCoordinates = [];
    _currentInstructionIndex = 0;

    var qs = new URLSearchParams({
        origin_lat: String(fromLat),
        origin_lng: String(fromLng),
        dest_lat: String(toLat),
        dest_lng: String(toLng)
    });
    var url = API_BASE_URL + '/api/webapp/order/' + encodeURIComponent(String(oid || '')) + '/driving-directions?' + qs.toString() + '&v=' + Date.now();
    if (WEBAPP_TOKEN) url += '&token=' + encodeURIComponent(WEBAPP_TOKEN);

    var controller = new AbortController();
    var timeoutId = setTimeout(function() { controller.abort(); }, 12000);

    var p = new Promise(function(resolve, reject) {
    fetch(url, { signal: controller.signal, headers: webappHeaders() })
        .then(function(r) { return r.json().then(function(data) { return { httpOk: r.ok, data: data }; }); })
        .then(function(wrapped) {
            clearTimeout(timeoutId);
            if (requestId !== _routeRequestId) {
                resolve(false);
                return;
            }
            var data = wrapped && wrapped.data;
            if (!wrapped || !wrapped.httpOk || !data || !data.ok || !data.coordinates || !data.coordinates.length) {
                console.warn('Google route failed → fallback', data && data.error);
                _clearRouteFetchCache();
                fallbackStraightLine(fromLat, fromLng, toLat, toLng);
                resolve(true);
                return;
            }
            routeRoadDistanceKm = typeof data.distance_km === 'number' && !isNaN(data.distance_km)
                ? data.distance_km
                : null;
            routeInstructions = [];
            routeCoordinates = [];
            _driverRouteCoords = data.coordinates.map(function(c) {
                return [Number(c[0]), Number(c[1])];
            }).filter(function(c) {
                return !isNaN(c[0]) && !isNaN(c[1]) && isValidCoord(c[1], c[0]);
            });
            // Close-the-gap: visually connect route to destination if OSRM ended early.
            // _driverRouteCoords is [lon, lat] order; toLat/toLng are in scope from drawRoute().
            if (_driverRouteCoords.length > 1 && toLat != null && toLng != null && isValidCoord(toLat, toLng)) {
                try {
                    var _lastPt = _driverRouteCoords[_driverRouteCoords.length - 1];
                    var _gapM = haversineM(_lastPt[1], _lastPt[0], toLat, toLng); // lat=index1, lon=index0
                    if (_gapM > 15 && _gapM < 40) {
                        _driverRouteCoords.push([toLng, toLat]); // push as [lon, lat]
                    }
                } catch (e) {}
            }
            var len = _driverRouteCoords.length;
            var midIdx = Math.floor(len / 2);
            var newHash = len + ':' +
                (_driverRouteCoords[0] || '') + ':' +
                (_driverRouteCoords[midIdx] || '') + ':' +
                (_driverRouteCoords[len - 1] || '');
            if (_routeHash !== newHash) {
                _smoothedRouteCoords = null;
                _routeHash = newHash;
            }
            routeCoordinates = _driverRouteCoords.map(function(c) { return [c[1], c[0]]; }); // [lat,lng]
            resetRouteProgress();
            if (data.steps && data.steps.length) {
                routeInstructions = data.steps.map(function(s) {
                    var idx = 0;
                    var best = Infinity;
                    for (var i = 0; i < _driverRouteCoords.length; i++) {
                        var c = _driverRouteCoords[i];
                        var d = haversineM(s.lat, s.lng, c[1], c[0]);
                        if (d < best) {
                            best = d;
                            idx = i;
                        }
                    }
                    var type = 0;
                    var mod = s.modifier || '';
                    if (mod && mod.includes('left')) type = -1;
                    else if (mod && mod.includes('right')) type = 1;
                    else type = 0;
                    return {
                        text: s.text,
                        type: type,
                        index: idx,
                        name: s.name || "",
                        distance: s.distance || 0
                    };
                });
                routeInstructions.push({
                    text: "🎯 Manzilga yetdingiz",
                    type: -1,
                    index: _driverRouteCoords.length - 1
                });
            } else {
                routeInstructions = buildPolylineManeuvers(routeCoordinates);
            }
            // Destination offset: if last segment is unnamed and short → stop 80m early
            _destOffsetActive = false;
            if (routeInstructions.length >= 2) {
                var _lastSeg = routeInstructions[routeInstructions.length - 2];
                var _lastSegNamed = _lastSeg.name && _lastSeg.name.length > 0;
                var _lastSegShort = _lastSeg.distance > 0 && _lastSeg.distance < 80;
                if (!_lastSegNamed && _lastSegShort) {
                    _destOffsetActive = true;
                }
            }
            _currentInstructionIndex = 0;
            if (!routeCoordinates.length || _driverRouteCoords.length < 2) {
                _clearRouteFetchCache();
                fallbackStraightLine(fromLat, fromLng, toLat, toLng);
                resolve(true);
                return;
            }
            _applyRouteGeometryToMap(fromLat, fromLng, toLat, toLng);
            _lastRouteUpdateTs = Date.now();
            _saveRouteFetchCache(fromLat, fromLng, toLat, toLng);
            resolve(true);
        })
        .catch(function(err) {
            clearTimeout(timeoutId);
            if (requestId !== _routeRequestId) {
                reject(false);
                return;
            }
            _clearRouteFetchCache();
            try {
                fallbackStraightLine(fromLat, fromLng, toLat, toLng);
            } catch (_) {}
            reject(err || new Error('Route fetch failed'));
        });
    });
    return p.finally(function() {
        if (requestId === _routeRequestId) {
            _routeInFlight = false;
        }
    });
}

/** Progressive polyline trim removed; route polyline stays full. No-op for existing call sites. */
function updateProgressiveRoute(driverLon, driverLat) {
    return;
}

function fallbackStraightLine(fromLat, fromLng, toLat, toLng) {
    var now = Date.now();
    var ROUTE_STALE_MS = 10000; // 10 seconds
    if (
        _driverRouteCoords &&
        _driverRouteCoords.length > 5 &&
        _lastRouteUpdateTs &&
        (now - _lastRouteUpdateTs < ROUTE_STALE_MS)
    ) {
        return;
    }
    _clearRouteFetchCache();
    routeCoordinates = [[fromLat, fromLng], [toLat, toLng]];
    // Build _driverRouteLine so the queue gate is satisfied and snapping works
    // on the straight-line fallback exactly the same as on a road polyline route.
    _driverRouteCoords = [[fromLng, fromLat], [toLng, toLat]];
    resetRouteProgress();
    if (typeof turf !== 'undefined' && _driverRouteCoords.length >= 2) {
        try { _driverRouteLine = turf.lineString(_driverRouteCoords); } catch (_) {}
    }
    _snapRouteLine = _driverRouteLine;
    routeRoadDistanceKm = haversineM(fromLat, fromLng, toLat, toLng) / 1000;
    routeInstructions = buildPolylineManeuvers(routeCoordinates);
    if (!routeInstructions.length) {
        routeInstructions = [{ text: "To'g'ri yo'l", type: -1, index: 0 }];
    }
    var fbPath = [
        { lat: fromLat, lng: fromLng },
        { lat: toLat, lng: toLng }
    ];
    _routeHash = null;
    _smoothedCoordsHash = null;
    setGoogleRoutePolyline(fbPath);
    setGoogleRouteABPolyline(fbPath);
    setTurnAndDistFromDriver({ lat: fromLat, lng: fromLng });
    updateNavUI();
    if (_pendingGps !== null) {
        var _pg = _pendingGps; _pendingGps = null;
        updateDriverMarker(_pg.lat, _pg.lng, _pg.heading);
    }
}

/** Reroute-only: 4s cooldown between allowed Google Directions calls (cost control). */

/**
 * Off-route detection: called after every GPS update during a trip.
 * Uses turf.pointToLineDistance from the raw GPS fix to _driverRouteLine.
 * Requires consecutive samples >= OFF_ROUTE_THRESHOLD_M before tryReroute (reduces GPS spike false positives).
 * tryReroute applies cooldown, in-flight guard, then drawRoute.
 */
async function tryReroute(lat, lng, opts = {}) { // FIXED: BUG#2
    const _now = Date.now();
    if (_rerouteInFlight && !opts?.force) return false;
    if (!opts?.force && (_now - __lastRerouteTs < 12000)) return false;
    if (ORDER_DATA?.destination_latitude != null) {
        const _distToDest = haversineM(lat, lng, ORDER_DATA.destination_latitude, ORDER_DATA.destination_longitude);
        if (_distToDest < 150) return false;
    }
    // FIXED: dead code from BUG#2 cleanup
    // update reroute tracking
    __lastRerouteTs = Date.now();
    _lastRerouteLat = lat;
    _lastRerouteLng = lng;

    _rerouteInFlight = true;
    try {
        resetRouteProgress();
        _snapRouteLine = null;
        const ok = await drawRoute(
            { lat: lat, lng: lng },
            {
                lat: ORDER_DATA.destination_latitude,
                lng: ORDER_DATA.destination_longitude
            },
            { fromReroute: true }
        );
        if (!ok) {
            fallbackStraightLine(
                lat, lng,
                ORDER_DATA.destination_latitude,
                ORDER_DATA.destination_longitude
            );
        }
        return true;
    } catch (e) {
        try {
            fallbackStraightLine(
                lat, lng,
                ORDER_DATA.destination_latitude,
                ORDER_DATA.destination_longitude
            );
        } catch (_) {}
        return true;
    } finally {
        _rerouteInFlight = false;
    }
}

function checkOffRoute(lat, lng, speed) {
    if (typeof turf === 'undefined') return;
    if (!_driverRouteLine || !_driverRouteLine.geometry) {
        return;
    }
    if (!ORDER_DATA ||
        !isValidCoord(ORDER_DATA.destination_latitude, ORDER_DATA.destination_longitude)) return;
    try {
        var distM = turf.pointToLineDistance(
            turf.point([lng, lat]),
            _driverRouteLine,
            { units: 'meters' }
        );
        if (distM >= OFF_ROUTE_THRESHOLD_M) {
            _offRouteCount++;
        } else {
            _offRouteCount = 0;
        }
        // Immediate reroute if very far off route
        if (distM > 150) {
            _offRouteCount = 0;
            tryReroute(lat, lng);
        } else if (_offRouteCount >= 3) { // FIXED: BUG#1
            _offRouteCount = 0;
            tryReroute(lat, lng);
        }
    } catch (_) {}
}

function drawRouteAB(fromA, toB) {
    if (!map || !fromA || !toB) return;
    var fromLat = fromA.lat != null ? fromA.lat : fromA[0];
    var fromLng = fromA.lng != null ? fromA.lng : fromA[1];
    var toLat = toB.lat != null ? toB.lat : toB[0];
    var toLng = toB.lng != null ? toB.lng : toB[1];
    setGoogleRouteABPolyline([
        { lat: fromLat, lng: fromLng },
        { lat: toLat, lng: toLng }
    ]);
}

async function handleArrived() {
    appState = 'ready';

    /* API call ??mijozga xabar */
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
            mapEaseToCamera({
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
    enableWakeLock();
    try {
        var _oid = (ORDER_DATA && ORDER_DATA.id != null) ? ORDER_DATA.id : ORDER_ID_CURRENT;
        if (_oid) localStorage.setItem('trip_active_order_id', String(_oid));
    } catch (_) {}
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
    try {
        var _tmOid = (ORDER_DATA && ORDER_DATA.id != null) ? ORDER_DATA.id : ORDER_ID_CURRENT;
        if (_tmOid && WEBAPP_TOKEN) {
            var _tmRes = await fetch(
                API_BASE_URL + '/api/webapp/order/' + _tmOid + '/trip-meter?v=' + Date.now(),
                { headers: webappHeaders() }
            );
            if (_tmRes.ok) {
                var _tmData = await _tmRes.json();
                if (_tmData && _tmData.active) {
                    if (_tmData.distance_km != null) tripData.distance = _tmData.distance_km;
                    if (!tripData.isWaiting) {
                        if (_tmData.waiting_seconds != null) tripData.waitingTime = _tmData.waiting_seconds;
                    }
                    tripData.isWaiting = !!_tmData.is_waiting;
                    tripData.surge = _tmData.surge_multiplier != null && _tmData.surge_multiplier !== undefined
                        ? Number(_tmData.surge_multiplier)
                        : (tripData.surge || 1);
                    if (_tmData.estimated_fare != null) tripData.serverFare = _tmData.estimated_fare;
                    updateTaximeter();
                }
            }
        }
    } catch (_tmE) {}
    startTripMeterPolling();
}

let waitingUITimer = null;
let waitingUIStart = null;

function startWaitingUI() {
    if (waitingUITimer) return;
    waitingUIStart = Date.now();
    waitingUITimer = setInterval(function() {
        var el = document.getElementById('waitingTimerUI');
        if (!el) return;
        var diff = Math.floor((Date.now() - waitingUIStart) / 1000);
        var m = String(Math.floor(diff / 60)).padStart(2, '0');
        var s = String(diff % 60).padStart(2, '0');
        el.textContent = m + ':' + s;
    }, 1000);
}

function stopWaitingUI() {
    if (waitingUITimer) {
        clearInterval(waitingUITimer);
        waitingUITimer = null;
    }
    waitingUIStart = null;
    var el = document.getElementById('waitingTimerUI');
    if (el) el.textContent = "00:00";
}

function toggleWaiting() {
    var wasWaiting = !!tripData.isWaiting;
    tripData.isWaiting = !wasWaiting;
    const btn = document.getElementById('waitingBtn');
    if (!btn) return;
    if (tripData.isWaiting) startWaitingUI();
    else stopWaitingUI();
    btn.textContent = tripData.isWaiting
        ? '▶ DAVOM ETISH'
        : '⏸ PAUZA / KUTISH';
    btn.className = tripData.isWaiting ? 'action-btn btn-success' : 'action-btn btn-warning';
    var oid = (ORDER_DATA && ORDER_DATA.id != null) ? ORDER_DATA.id : ORDER_ID_CURRENT;
    if (oid && WEBAPP_TOKEN) {
        if (tripData.isWaiting) {
            if (toggleWaiting._waitingTimer) return; // prevent duplicate timers
            fetch(API_BASE_URL + '/api/webapp/order/' + oid + '/trip/pause?v=' + Date.now(), {
                method: 'POST',
                headers: webappHeaders()
            }).catch(function() {});
        } else {
            if (toggleWaiting._waitingTimer) {
                clearTimeout(toggleWaiting._waitingTimer);
                toggleWaiting._waitingTimer = null;
            }
            _resumeInFlight = true;
            fetch(API_BASE_URL + '/api/webapp/order/' + oid + '/trip/resume?v=' + Date.now(), {
                method: 'POST',
                headers: webappHeaders()
            })
                .then(function() {
                    return fetch(API_BASE_URL + '/api/webapp/order/' + oid + '/trip-meter?v=' + Date.now(), {
                        headers: webappHeaders()
                    });
                })
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (data && data.active) {
                        tripData.waitingTime = data.waiting_seconds || tripData.waitingTime;
                        tripData.serverFare = (data.estimated_fare != null ? data.estimated_fare : null);
                    }
                })
                .finally(function() {
                    _resumeInFlight = false;
                    updateTaximeter();
                })
                .catch(function() {
                    _resumeInFlight = false;
                });
            return;
        }
    }
    updateTaximeter();
}

function safeAlert(msg, cb) { alert(msg); if (cb) cb(); }
function safeConfirm(msg, onOk) { if (confirm(msg)) onOk(); }
function handleFinish() {
    safeConfirm("Safarni yakunlab, tolovni oldingizmi?", finishTrip);
}

async function finishTrip() {
    var orderId = ORDER_ID_CURRENT;
    if (!orderId) { safeAlert("Order ID topilmadi."); return; }
    if (tripData.serverFare == null || isNaN(Number(tripData.serverFare))) {
        safeAlert("Server narxi tayyor emas. Internetni tekshiring yoki biroz kuting.");
        return;
    }
    var distKm = tripData.distance;
    var item = {
        orderId: orderId,
        display_fare: tripData.serverFare,
        distance_km: distKm,
        token: WEBAPP_TOKEN || '',
        apiBaseUrl: API_BASE_URL
    };
    enqueuePendingTrip(item);
    updateSyncUI();

    var loadEl = document.getElementById('loading');
    if (loadEl) loadEl.classList.remove('hidden');
    try {
        await flushPendingTrips();
    } finally {
        if (loadEl) loadEl.classList.add('hidden');
    }

    var stillPending = getPendingTrips().some(function(x) { return String(x.orderId) === String(orderId); });
    if (stillPending) {
        safeAlert("Internet yo'q yoki server javob bermadi. Ma'lumot saqlandi ??ulanish tiklanganda avtomatik yuboriladi.");
    } else {
        try { localStorage.removeItem('trip_active_order_id'); } catch (_) {}
        disableWakeLock();
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
    var tripTimeEl = document.getElementById('tripTime');
    if (tripTimeEl) tripTimeEl.textContent = `${m}:${s}`;

    updateTaximeter();
}

/** Faqat server estimated_fare (HALF_UP 100) — klient hisoblamaydi. */
function updateTaximeter() {
    var curFareEl = document.getElementById('currentFare');
    var tripDistEl = document.getElementById('tripDistance');
    if (tripDistEl) tripDistEl.textContent = tripData.distance.toFixed(2);
    if (!curFareEl) return;
    if (TARIFF_LOAD_ERROR) {
        console.warn("Tariff load error, but showing server fare");
    }
    var sf = tripData.serverFare;
    if (window.DEBUG) {
        console.log("[TRIP_METER_RENDER]", {
            serverFare: tripData.serverFare,
            distance: tripData.distance,
            waitingTime: tripData.waitingTime,
            isWaiting: tripData.isWaiting
        });
    }
    // Waiting visual feedback (UI only)
    try {
        var wbtn = document.getElementById('waitingBtn');
        if (wbtn) {
            wbtn.style.transition = 'opacity 200ms ease';
            if (tripData.isWaiting) {
                // Blink subtly once per second (driven by updateTimer)
                wbtn.style.opacity = (Math.floor(Date.now() / 500) % 2 === 0) ? '1' : '0.65';
            } else {
                wbtn.style.opacity = '1';
            }
        }
        curFareEl.style.transition = 'color 200ms ease';
        curFareEl.style.color = tripData.isWaiting ? '#f59e0b' : '';
    } catch (_) {}

    // Smooth fare display (visual only). Never compute fare locally.
    var nextTarget = (sf != null && !isNaN(Number(sf))) ? Math.round(Number(sf)) : null;
    if (nextTarget != null) {
        if (_fareUI.target == null) {
            _fareUI.displayed = nextTarget;
            _fareUI.target = nextTarget;
        } else if (_fareUI.target !== nextTarget) {
            if (_fareUI.raf != null) { cancelAnimationFrame(_fareUI.raf); _fareUI.raf = null; }
            _fareUI.from = (_fareUI.displayed != null ? _fareUI.displayed : _fareUI.target);
            _fareUI.target = nextTarget;
            _fareUI.startTs = 0;
        }
    }

    // Failsafe: if serverFare missing, keep previous displayed value (do not reset UI).
    if (_fareUI.displayed == null && _fareUI.target == null) {
        return;
    }

    function _renderFare(n) {
        const step = 100;
        const stepped = Math.floor(Number(n) / step) * step;
        curFareEl.textContent = stepped.toLocaleString('en-US');
    }

    function _tick(ts) {
        if (_fareUI.startTs === 0) _fareUI.startTs = ts;
        var fromV = (_fareUI.from != null ? _fareUI.from : (_fareUI.displayed != null ? _fareUI.displayed : _fareUI.target));
        var toV = (_fareUI.target != null ? _fareUI.target : fromV);
        var t = (ts - _fareUI.startTs) / (_fareUI.durMs || 1);
        if (t >= 1) {
            _fareUI.displayed = toV;
            _fareUI.from = null;
            _fareUI.startTs = 0;
            _renderFare(_fareUI.displayed);
            _fareUI.raf = null;
            return;
        }
        // Ease-out cubic for smooth finish
        var p = 1 - Math.pow(1 - Math.max(0, Math.min(1, t)), 3);
        _fareUI.displayed = fromV + (toV - fromV) * p;
        _renderFare(_fareUI.displayed);
        _fareUI.raf = requestAnimationFrame(_tick);
    }

    // If no animation in progress, render once; else keep animating.
    if (_fareUI.target != null && (_fareUI.from != null || _fareUI.displayed !== _fareUI.target)) {
        if (_fareUI.raf != null) { cancelAnimationFrame(_fareUI.raf); _fareUI.raf = null; }
        _fareUI.raf = requestAnimationFrame(_tick);
        return;
    }

    _fareUI.displayed = (_fareUI.target != null ? _fareUI.target : _fareUI.displayed);
    _renderFare(_fareUI.displayed);
}

window.addEventListener('online', async () => {
    updateSyncUI();
    flushPendingTrips();
    if (appState === 'trip' && ORDER_DATA && ORDER_DATA.id) {
        try {
            const res = await fetch(
                API_BASE_URL + '/api/webapp/order/' + ORDER_DATA.id + '/trip-meter?v=' + Date.now(),
                { headers: webappHeaders() }
            );
            if (!res.ok) return;
            const data = await res.json();
            if (data && data.active) {
                tripData.distance = data.distance_km || 0;
                if (!tripData.isWaiting) {
                    tripData.waitingTime = data.waiting_seconds || 0;
                }
                tripData.isWaiting = !!data.is_waiting;
                tripData.surge = data.surge_multiplier != null && data.surge_multiplier !== undefined ? Number(data.surge_multiplier) : (tripData.surge || 1);
                if (data.estimated_fare != null) tripData.serverFare = data.estimated_fare;
                updateTaximeter();
            }
        } catch (e) {
            console.warn('Online resync failed', e);
        }
    }
});
window.addEventListener('offline', function() {
    updateSyncUI();
});
document.addEventListener('visibilitychange', async () => {
    if (document.visibilityState === 'visible') {
        if (map) mapResize();
        updateSyncUI();
        flushPendingTrips();
        if (appState === 'trip') {
            enableWakeLock();
        }
    }
});
window.addEventListener('resize', function() {
    if (map) mapResize();
});

window.onload = init;
