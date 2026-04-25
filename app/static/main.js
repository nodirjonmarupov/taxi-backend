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
/** Taksometr: narx faqat server /trip-meter estimated_fare dan (hardcoded tariff yo'q). */
let TARIFF = null;
let TARIFF_LOAD_ERROR = false;
let ORDER_DATA = null;
const tg = (window.Telegram && window.Telegram.WebApp) ? window.Telegram.WebApp : { expand: function(){}, ready: function(){} };

let map, driverMarker, clientMarker, destMarker;
let _gRoutePolyline = null;
let _gRouteShadow = null;
let _gRouteAbPolyline = null;
let routeRoadDistanceKm = null;
let routeInstructions = [], routeCoordinates = [];
// Turf route line feature (haydovchi uchun snapping va progressive trim)
let _driverRouteLine = null;       // turf.lineString ??[lon,lat] koordinatlarda
let _driverRouteCoords = [];       // [[lon,lat], ...] — route polyline (GeoJSON tartib)
let _smoothedRouteCoords = null;
let _routeHash = null;
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
let _velLat = 0, _velLng = 0;
let _smoothVelLat = 0, _smoothVelLng = 0;
let _gpsAnchorLat = null, _gpsAnchorLng = null, _gpsAnchorMs = 0;
let _predLat = null, _predLng = null;
let _routeAnchorIdx = 0;
let _currentInstructionIndex = 0; // next maneuver in routeInstructions; only advances forward
let _stableZoom = null; // EMA-smoothed zoom; prevents per-frame flicker at speed boundaries
let _lastNavUpdate = 0;      // throttle nav UI (~10 FPS adaptive)
let _lastSnapUpdate = 0;     // throttle Turf nav snap (~10 FPS adaptive)
let _lastPredSnapUpdate = 0; // throttle Turf prediction snap (~10 FPS)
let _lastTurnI = null;       // DOM cache: suppress updateNavUI when nothing changed
let _lastDist = null;
let _displayArrowBrg = null;
let _lastStableLat = null;
let _lastStableLng = null;
let _pendingGps = null;    // queued GPS update received before _driverRouteLine was ready
let _snapRouteLine = null;  // trimmed forward-only snap line; rebuilt after each snap
let _offRouteCount = 0;       // consecutive GPS samples past off-route threshold (noise filter)
let _lastRerouteTime = 0;     // last reroute attempt timestamp (cooldown)
let _rerouteInFlight = false; // single in-flight directions request for reroute
let _routeInFlight = false;   // global mutex: any drawRoute directions fetch
/** Last successful road route (avoid duplicate Directions calls for tiny GPS jitter). */
let _routeFetchCache = null;
var ROUTE_MIN_API_SEGMENT_M = 50;
var ROUTE_SAME_ENDPOINT_M = 10;
var ROUTE_CACHE_NEAR_M = 50;
var OFF_ROUTE_THRESHOLD_M = 60;
let _lastProgressLat = null;
let _lastProgressLng = null;
let _lastProgressAnchorIdx = null;
let _lastDbgLat = null;
let _lastDbgLng = null;
let _dispLat = null;
let _dispLng = null;
let _debugSnapCompareCounter = 0;
let _dispArrowDeg = null;
let _wakeLock = null;
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
            _wakeLock.addEventListener('release', function() {
                _wakeLock = null;
            });
        }
    } catch (err) {
        console.warn('WakeLock failed', err);
    }
}

async function disableWakeLock() {
    try {
        if (_wakeLock) {
            await _wakeLock.release();
            _wakeLock = null;
        }
    } catch (err) {
        console.warn('WakeLock release failed', err);
    }
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
        var d = haversineM(lat, lng, py, px); // metric distance ??correct basis for comparison
        if (d < bd) { bd = d; best = [py, px]; bestIdx = i; }
    }
    if (best && bd < ROUTE_SNAP_MAX_M) return [best[0], best[1], bestIdx];
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
        clickableIcons: false,
        mapTypeId: 'roadmap'
    });
    try { map.setTilt(45); } catch (_) {}
    return map;
}
function mapResize() {
    if (map && _mapsJsReady()) {
        try { google.maps.event.trigger(map, 'resize'); } catch (_) {}
    }
}
function mapEaseToCamera(opts) {
    if (!map || !_mapsJsReady()) return;
    var c = opts.center;
    var lat = Array.isArray(c) ? c[1] : c.lat;
    var lng = Array.isArray(c) ? c[0] : c.lng;
    var ll = new google.maps.LatLng(lat, lng);
    var dur = opts.duration != null ? opts.duration : 350;
    if (dur === 0) {
        map.setCenter(ll);
        if (opts.zoom != null) map.setZoom(opts.zoom);
        try { if (opts.bearing != null) map.setHeading(opts.bearing); } catch (_) {}
        try { if (opts.pitch != null) map.setTilt(opts.pitch); } catch (_) {}
        return;
    }
    map.setCenter(ll);
    if (opts.zoom != null) map.setZoom(opts.zoom);
    try { if (opts.bearing != null) map.setHeading(opts.bearing); } catch (_) {}
    try { if (opts.pitch != null) map.setTilt(opts.pitch); } catch (_) {}
}
function updateCamera(lat, lng, heading) {
    if (!map || !_mapsJsReady()) return;

    // smooth follow (keep existing smoothing vars)
    if (_camLat === null) {
        _camLat = lat;
        _camLng = lng;
    }

    _camLat += (lat - _camLat) * 0.15;
    _camLng += (lng - _camLng) * 0.15;

    // 🔥 forward offset (REAL 3D effect)
    var offset = 0.0008;
    var rad = heading * Math.PI / 180;

    var camLat = _camLat + Math.cos(rad) * offset;
    var camLng = _camLng + Math.sin(rad) * offset;

    map.setCenter({ lat: camLat, lng: camLng });

    try { map.setHeading(heading); } catch (_) {}
    try { map.setTilt(60); } catch (_) {}
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
    if (!_smoothedRouteCoords || _smoothedRouteCoords.length !== _driverRouteCoords.length) {
        _smoothedRouteCoords = smoothCoords(_driverRouteCoords, 2);
    }
    var path = pathLatLngFromLngLatPairs(_smoothedRouteCoords);
    if (path.length) setGoogleRoutePolyline(path);
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
function setGoogleRoutePolyline(path) {
    if (!map || !_mapsJsReady() || !path || !path.length) return;
    if (!_gRoutePolyline) {
        _gRouteShadow = new google.maps.Polyline({
            path: path,
            map: map,
            strokeColor: '#000000',
            strokeOpacity: 0.25,
            strokeWeight: 10,
            geodesic: true
        });
        _gRoutePolyline = new google.maps.Polyline({
            path: path,
            map: map,
            geodesic: true,
            strokeColor: '#FFD600',
            strokeWeight: 6,
            strokeOpacity: 0.9
        });
    } else {
        if (_gRouteShadow) {
            _gRouteShadow.setPath(path);
            _gRouteShadow.setMap(map);
        }
        _gRoutePolyline.setPath(path);
        _gRoutePolyline.setMap(map);
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
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('class', 'dm-arrow');
    svg.innerHTML = '<path d="M12 2L4.5 20.29l.71.71L12 18l6.79 3 .71-.71z"/>';
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
            zoom: zoom,
            duration: 350
        });
    } else if (lastDriverLocation && map) {
        mapEaseToCamera({
            center: [lastDriverLocation.lon, lastDriverLocation.lat],
            zoom: map.getZoom() || 17,
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


        // updateBearing ?????????????????????????????????????????????????????????
        // ?_brg = 0.80 - 0.65 횞 min(spd/30, 1)
        // ? at  0 km/h: 0.80s ??absorbs GPS bearing noise when nearly stopped.
        // ? at 30 km/h: 0.15s ??tracks highway bends without lag.
        // ? at 60 km/h: 0.15s ??capped; faster would overshoot sharp turns.
        if (!useManualBearing) targetBearing = northUpMode ? 0 : brg;
        var _tauBrg = 0.80 - 0.65 * Math.min(spd / 30, 1);
        var _brgDecay = Math.exp(-dt / _tauBrg);
        var _brgShortcut = ((targetBearing - displayBearing + 540) % 360) - 180;
        displayBearing = (displayBearing + _brgShortcut * (1 - _brgDecay) + 360) % 360;

        // SINGLE SOURCE BEARING (route-based)
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

        // Arrow heading: adaptive tau to reduce low-speed jitter.
        var _tauHead = spd < 5 ? 0.25 : spd < 20 ? 0.15 : 0.10;
        var _headDecay = Math.exp(-dt / _tauHead);
        var _hdShortcut = ((brg - displayHeading + 540) % 360) - 180;
        displayHeading = (displayHeading + _hdShortcut * (1 - _headDecay) + 360) % 360;
        console.log(
            '[FRAME]',
            'spd=', spd,
            'move(m)=', (dLat != null && dLng != null && _lastDbgLat != null && _lastDbgLng != null ? haversineM(dLat, dLng, _lastDbgLat, _lastDbgLng).toFixed(2) : 'na'),
            'brg=', (typeof brg === 'number' ? brg.toFixed(1) : 'na'),
            'head=', (typeof displayHeading === 'number' ? displayHeading.toFixed(1) : 'na'),
            'anchor=', _routeAnchorIdx
        );
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
            driverMarker.setLngLat([_dispLng, _dispLat]);

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
            var _snapInterval = spd < 5 ? 150 : 80;
            var _navInterval  = spd < 5 ? 150 : 80;
            if (_nowMs - _lastSnapUpdate > _snapInterval) {
                // Nav-progress Turf snap: throttled adaptively.
                if (typeof turf !== 'undefined' && _driverRouteLine && _driverRouteLine.geometry) {
                    try {
                        var _navSnap = turf.nearestPointOnLine(_driverRouteLine, turf.point([dLng, dLat]));
                        if (_navSnap && _navSnap.properties && _navSnap.properties.index != null) {
                            var _maxIdx = _driverRouteCoords.length > 1 ? _driverRouteCoords.length - 2 : 0;
                            var _newIdx = Math.min(_navSnap.properties.index, _maxIdx);
                            if (typeof _routeAnchorIdx === 'number' && !isNaN(_routeAnchorIdx) && _newIdx < _routeAnchorIdx) {
                                var diff = _routeAnchorIdx - _newIdx;

                                // Allow real backward jump if it's large (actual turn)
                                if (diff < 2) {
                                    _newIdx = _routeAnchorIdx;
                                }
                            }

                            _routeAnchorIdx = _newIdx;
                            console.log('[ANCHOR UPDATE]', _routeAnchorIdx);
                        }
                    } catch (_) {}
                }
                _lastSnapUpdate = _nowMs;
            }
            if (_nowMs - _lastNavUpdate > _navInterval) {
                setTurnAndDistFromDriver({ lat: dLat, lng: dLng });
                // DOM guard: skip repaint when turn index and distance haven't meaningfully changed.
                if (turnI !== _lastTurnI || _lastDist === null || Math.abs(distKm - _lastDist) > 0.01) {
                    updateNavUI();
                    _lastTurnI = turnI;
                    _lastDist  = distKm;
                }
                _lastNavUpdate = _nowMs;
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
            var _brgDelta = Math.abs(((displayBearing - _lastCamBrg + 540) % 360) - 180);
            var _moveDist = (_lastCamLat != null && _lastCamLng != null)
                ? haversineM(dLat, dLng, _lastCamLat, _lastCamLng) : 999;
            var _moved = _moveDist > 1;
            var _zoomDelta = Math.abs(_zoom - _lastCamZoom);
            if ((_nowMs - _lastCamUpdate > 130) &&
                (_moved || _brgDelta > 2 || _zoomDelta > 0.1)) {
                if (Date.now() >= _camBlockUntil) {
                    var currentHeading = displayBearing;
                    if (_lastCamLat != null && _lastCamLng != null) {
                        var deltaLat = dLat - _lastCamLat;
                        var deltaLng = dLng - _lastCamLng;
                        currentHeading = (Math.atan2(deltaLng, deltaLat) * 180 / Math.PI + 360) % 360;
                    }
                    updateCamera(dLat, dLng, currentHeading);

                    _lastCamLat = dLat;
                    _lastCamLng = dLng;
                    _lastCamUpdate = _nowMs;
                }
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

    google.maps.event.addListener(map, 'dragstart', function() { _temporarilyDisableFollow(5000); });

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
    try {
        var z = map.getZoom();
        if (z != null && z > 16) map.setZoom(16);
    } catch (_) {}
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
        var _prevTrimLineForDbg = _snapRouteLine;
        var _prevSnappedLat = tLat, _prevSnappedLng = tLng;
        var sl = lat, sa = lng;
        if (typeof turf !== 'undefined' && _driverRouteLine && _driverRouteLine.geometry) {
            try {
                var _snapPt = turf.point([lng, lat]);
                var _snapRes = turf.nearestPointOnLine(_driverRouteLine, _snapPt, { units: 'kilometers' });
                if (_snapRes && _snapRes.geometry && _snapRes.geometry.coordinates) {
                    sa = _snapRes.geometry.coordinates[0];
                    sl = _snapRes.geometry.coordinates[1];
                    // #region agent log
                    try {
                        _debugSnapCompareCounter++;
                        if (_debugSnapCompareCounter % 25 === 0) {
                            var _ptrim = _prevTrimLineForDbg;
                            var _divergeM = null;
                            if (_ptrim && _ptrim.geometry && _ptrim !== _driverRouteLine) {
                                var _tn = turf.nearestPointOnLine(_ptrim, _snapPt, { units: 'kilometers' });
                                if (_tn && _tn.geometry && _tn.geometry.coordinates) {
                                    _divergeM = haversineM(sl, sa, _tn.geometry.coordinates[1], _tn.geometry.coordinates[0]);
                                }
                            }
                            fetch('http://127.0.0.1:7602/ingest/b6487788-bee6-445f-81f9-95a1b43ce854',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'4d6510'},body:JSON.stringify({sessionId:'4d6510',location:'main.js:updateDriverMarker',message:'fullLineVsPrevTrimSnap',data:{divergeM:_divergeM,anchorBefore:_routeAnchorIdx,fullSnapIdx:_snapRes.properties&&_snapRes.properties.index!=null?_snapRes.properties.index:null,trimWasSameRef:_ptrim===_driverRouteLine},timestamp:Date.now(),hypothesisId:'H1'})}).catch(function(){});
                        }
                        if ((!_snapRes.properties || _snapRes.properties.index == null) && _debugSnapCompareCounter % 30 === 0) {
                            fetch('http://127.0.0.1:7602/ingest/b6487788-bee6-445f-81f9-95a1b43ce854',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'4d6510'},body:JSON.stringify({sessionId:'4d6510',location:'main.js:updateDriverMarker',message:'snapMissingRouteIndex',data:{},timestamp:Date.now(),hypothesisId:'H3'})}).catch(function(){});
                        }
                    } catch (_lg) {}
                    // #endregion
                    if (_snapRes.properties && _snapRes.properties.index != null) {
                        var _maxIdx = _driverRouteCoords.length > 1 ? _driverRouteCoords.length - 2 : 0;
                        var _newIdx = Math.min(_snapRes.properties.index, _maxIdx);
                        if (typeof _routeAnchorIdx === 'number' && !isNaN(_routeAnchorIdx) && _newIdx < _routeAnchorIdx) {
                            var diff = _routeAnchorIdx - _newIdx;
                            if (diff < 2) {
                                _newIdx = _routeAnchorIdx;
                            }
                        }
                        _routeAnchorIdx = _newIdx;
                        console.log('[ANCHOR UPDATE]', _routeAnchorIdx);
                        var _trimCoords = [[sa, sl]].concat(_driverRouteCoords.slice(_routeAnchorIdx + 1));
                        if (_trimCoords.length >= 2) {
                            try { _snapRouteLine = turf.lineString(_trimCoords); } catch (_) {}
                            // #region agent log
                            if (_debugSnapCompareCounter % 27 === 0) {
                                fetch('http://127.0.0.1:7602/ingest/b6487788-bee6-445f-81f9-95a1b43ce854',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'4d6510'},body:JSON.stringify({sessionId:'4d6510',location:'main.js:updateDriverMarker',message:'trimLineShape',data:{trimVertexCount:_trimCoords.length,driverVertexCount:_driverRouteCoords.length,anchor:_routeAnchorIdx},timestamp:Date.now(),hypothesisId:'H2'})}).catch(function(){});
                            }
                            // #endregion
                        }
                    }
                }
            } catch (_e) {
                if (routeCoordinates && routeCoordinates.length >= 2) {
                    var _fb = snapToRoute(lat, lng);
                    sl = _fb[0]; sa = _fb[1]; _routeAnchorIdx = _fb[2];
                    console.log('[ANCHOR UPDATE]', _routeAnchorIdx);
                }
            }
        } else if (routeCoordinates && routeCoordinates.length >= 2) {
            var _fb2 = snapToRoute(lat, lng);
            sl = _fb2[0]; sa = _fb2[1]; _routeAnchorIdx = _fb2[2];
            console.log('[ANCHOR UPDATE]', _routeAnchorIdx);
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
        // _routeAnchorIdx is now set at snap time (from Turf's properties.index or
        // snapToRoute's return value). No secondary vertex search needed here.
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
        if (appState === 'arriving' || appState === 'ready') {
            var clPos = (clientMarker && clientMarker.getLngLat) ? clientMarker.getLngLat() : { lat: ORDER_DATA.pickup_latitude, lng: ORDER_DATA.pickup_longitude };
            if (clPos) {
                var straightM = haversineM(driverPos.lat, driverPos.lng, clPos.lat, clPos.lng);
                var d = (routeRoadDistanceKm != null && routeRoadDistanceKm > 0) ? routeRoadDistanceKm : (straightM / 1000);
                if (d > MAX_DISTANCE_KM || d < 0 || isNaN(d)) d = 0;
                var distEl = document.getElementById('distanceToClient');
                var timeEl = document.getElementById('timeToClient');
                if (distEl) distEl.textContent = d > MAX_DISTANCE_KM ? '0.00' : d.toFixed(2);
                if (timeEl) timeEl.textContent = d > MAX_DISTANCE_KM ? '??' : '~' + Math.max(1, Math.round(d / AVG_SPEED_KMH * 60));
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

                if (snap.properties && snap.properties.index != null) {
                    var _maxIdxRa = _driverRouteCoords.length > 1 ? _driverRouteCoords.length - 2 : 0;
                    _routeAnchorIdx = Math.min(snap.properties.index, _maxIdxRa);
                    console.log('[ANCHOR UPDATE]', _routeAnchorIdx);
                }

            }
        } catch (_) {}
    }
    if (_pendingGps !== null) {
        var _pg = _pendingGps; _pendingGps = null;
        updateDriverMarker(_pg.lat, _pg.lng, _pg.heading);
    }
    setMainRoutePolylineFromDriverCoords();
    setTurnAndDistFromDriver({ lat: fromLat, lng: fromLng });
    updateNavUI();
}

function drawRoute(from, to, opts) {
    opts = opts || {};
    if (!map || !from || !to) return Promise.resolve(false);
    if (_routeInFlight) return Promise.resolve(false);
    if (_rerouteInFlight && !opts.fromReroute) return Promise.resolve(false);

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
            var data = wrapped && wrapped.data;
            var stripHtml = function(s) {
                if (!s) return '';
                return String(s).replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();
            };
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
            (data.instructions || []).forEach(function(step, idx) {
                routeInstructions.push({
                    text: stripHtml(step.text || ''),
                    type: (step.type != null && typeof step.type === 'number') ? step.type : -1,
                    index: step.index != null ? step.index : idx
                });
            });
            _driverRouteCoords = data.coordinates.map(function(c) {
                return [Number(c[0]), Number(c[1])];
            }).filter(function(c) {
                return !isNaN(c[0]) && !isNaN(c[1]) && isValidCoord(c[1], c[0]);
            });
            var newHash = _driverRouteCoords.length + ':' +
                (_driverRouteCoords.length ? _driverRouteCoords[0] : '') + ':' +
                (_driverRouteCoords.length ? _driverRouteCoords[_driverRouteCoords.length - 1] : '');
            if (_routeHash !== newHash) {
                _smoothedRouteCoords = null;
                _routeHash = newHash;
            }
            routeCoordinates = _driverRouteCoords.map(function(c) { return [c[1], c[0]]; }); // [lat,lng]
            resetRouteProgress();
            if (!routeCoordinates.length || _driverRouteCoords.length < 2) {
                _clearRouteFetchCache();
                fallbackStraightLine(fromLat, fromLng, toLat, toLng);
                resolve(true);
                return;
            }
            _applyRouteGeometryToMap(fromLat, fromLng, toLat, toLng);
            _saveRouteFetchCache(fromLat, fromLng, toLat, toLng);
            resolve(true);
        })
        .catch(function(err) {
            clearTimeout(timeoutId);
            _clearRouteFetchCache();
            try {
                fallbackStraightLine(fromLat, fromLng, toLat, toLng);
            } catch (_) {}
            reject(err || new Error('Route fetch failed'));
        });
    });
    return p.finally(function() {
        _routeInFlight = false;
    });
}

/**
 * Progressive trim: haydovchi o'tib ketgan yo'l qismini o'chirib,
 * faqat haydovchidan pickup gacha sariq chiziqni xaritada ko'rsatadi.
 * driverLon, driverLat ??snapped yoki GPS koordinatalar [lon, lat].
 */
function updateProgressiveRoute(driverLon, driverLat) {
    if (!_driverRouteCoords || _driverRouteCoords.length < 2) return;
    if (typeof _routeAnchorIdx !== 'number' || isNaN(_routeAnchorIdx)) return;

    var idx = Math.max(0, Math.min(_routeAnchorIdx, _driverRouteCoords.length - 2));
    if (_lastProgressAnchorIdx !== null && idx <= _lastProgressAnchorIdx) return;

    // TEMP DISABLED: progressive route drawing
    return;

    _lastProgressAnchorIdx = idx;
    _lastProgressLat = driverLat;
    _lastProgressLng = driverLon;
}

function fallbackStraightLine(fromLat, fromLng, toLat, toLng) {
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
    routeInstructions = [{ text: "To'g'ri yo'l", type: -1, index: 0 }];
    _currentInstructionIndex = 0;
    var fbPath = [
        { lat: fromLat, lng: fromLng },
        { lat: toLat, lng: toLng }
    ];
    setGoogleRoutePolyline(fbPath);
    setGoogleRouteABPolyline(fbPath);
    setTurnAndDistFromDriver({ lat: fromLat, lng: fromLng });
    updateNavUI();
    if (_pendingGps !== null) {
        var _pg = _pendingGps; _pendingGps = null;
        updateDriverMarker(_pg.lat, _pg.lng, _pg.heading);
    }
}

/** Reroute-only: 10s cooldown between allowed Google Directions calls (cost control). */
var ROUTE_REROUTE_COOLDOWN_MS = 10000;
function shouldReroute() {
    var now = Date.now();
    if (now - _lastRerouteTime < ROUTE_REROUTE_COOLDOWN_MS) return false;
    _lastRerouteTime = now;
    return true;
}

/**
 * Off-route detection: called after every GPS update during a trip.
 * Uses turf.pointToLineDistance from the raw GPS fix to _driverRouteLine.
 * Requires two consecutive samples >= OFF_ROUTE_THRESHOLD_M before tryReroute (reduces GPS spike false positives).
 * tryReroute applies cooldown, in-flight guard, then drawRoute.
 */
async function tryReroute(lat, lng) {
    if (_rerouteInFlight) return false;
    if (_routeInFlight) return false;
    if (!shouldReroute()) return false;

    _rerouteInFlight = true;

    try {
        _routeAnchorIdx = 0;
        resetRouteProgress();
        console.log('[ANCHOR UPDATE]', _routeAnchorIdx);
        _snapRouteLine = null;
        var routed = await drawRoute(
            { lat: lat, lng: lng },
            {
                lat: ORDER_DATA.destination_latitude,
                lng: ORDER_DATA.destination_longitude
            },
            { fromReroute: true }
        );
        if (!routed) return false;
        return true;
    } catch (e) {
        console.warn('Reroute failed', e);
        _lastRerouteTime = Date.now() - 3000;
        return false;
    } finally {
        _rerouteInFlight = false;
    }
}

function checkOffRoute(lat, lng, speed) {
    if (appState !== 'trip') return;
    if (typeof turf === 'undefined') return;
    if (!_driverRouteLine || !_driverRouteLine.geometry) return;
    if (!ORDER_DATA ||
        !isValidCoord(ORDER_DATA.destination_latitude, ORDER_DATA.destination_longitude)) return;
    if (typeof speed !== 'undefined' && speed !== null && !isNaN(speed) && speed < 3) return;

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

        if (_offRouteCount >= 2) {
            tryReroute(lat, lng).then(function(triggered) {
                if (triggered) {
                    _offRouteCount = 0;
                }
            });
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

function toggleWaiting() {
    tripData.isWaiting = !tripData.isWaiting;
    const btn = document.getElementById('waitingBtn');
    if (!btn) return;
    btn.textContent = tripData.isWaiting
        ? '▶ DAVOM ETISH'
        : '⏸ PAUZA / KUTISH';
    btn.className = tripData.isWaiting ? 'action-btn btn-success' : 'action-btn btn-warning';
    var oid = (ORDER_DATA && ORDER_DATA.id != null) ? ORDER_DATA.id : ORDER_ID_CURRENT;
    if (oid && WEBAPP_TOKEN) {
        if (tripData.isWaiting) {
            fetch(API_BASE_URL + '/api/webapp/order/' + oid + '/trip/pause?v=' + Date.now(), {
                method: 'POST',
                headers: webappHeaders()
            }).catch(function() {});
        } else {
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
