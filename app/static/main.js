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

let map, driverMarker, clientMarker, destMarker;
let routeRoadDistanceKm = null;
let routeInstructions = [], routeCoordinates = [];
// Turf route line feature (haydovchi uchun snapping va progressive trim)
let _driverRouteLine = null;       // turf.lineString ??[lon,lat] koordinatlarda
let _driverRouteCoords = [];       // [[lon,lat], ...] ??OSRM raw coords (GeoJSON tartib)
let arrowEl = null;
let tLat = null, tLng = null, dLat = null, dLng = null, brg = 0, spd = 0;
let pLat = null, pLng = null, locked = true;
let simIdx = 0, simOn = false, simTmr = null, turnI = 0, distKm = 1;
let displayBearing = 0, targetBearing = 0;
let displayHeading = 0;
let _camBlockUntil = 0;
let _lastCamLat = null, _lastCamLng = null, _lastCamBrg = 0, _lastCamZoom = 0;
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
let _firstSnapDone = false; // true after the first successful Turf snap; guards dead zone
let _snapRouteLine = null;  // trimmed forward-only snap line; rebuilt after each snap
let _offRouteCount = 0;       // consecutive GPS samples past off-route threshold (noise filter)
let _lastRerouteTime = 0;     // last reroute attempt timestamp (cooldown)
let _rerouteInFlight = false; // single in-flight OSRM request for reroute
let _routeInFlight = false;   // global mutex: any drawRoute OSRM fetch
let _lastProgressLat = null;
let _lastProgressLng = null;
let _lastProgressAnchorIdx = null;
let _lastDbgLat = null;
let _lastDbgLng = null;
let _lastDisplayUpdate = 0;
let _prevSpdForDisplay = 0;
let _dispLat = null;
let _dispLng = null;
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
let intervals = { timer: null, position: null };

const API_BASE_URL = window.__WEBAPP_BASE_URL__ || window.location.origin;
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
let lastSentLocation = null;
let lastSentTime = 0;
const MIN_DISTANCE_M = 15;
const ROUTE_SNAP_MAX_M = 20;
const RAW_GPS_MIN_MOVE_M = 5;
const RAW_GPS_REF_FREEZE_MAX_KMH = 6;
const RAW_GPS_HOLD_MAX_KMH = 12;
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
        rotationAlignment: 'viewport', // viewport: MapLibre elementga o'z rotation qo'shmaydi ??CSS bilan to'liq nazorat
        pitchAlignment: 'viewport'
    }).setLngLat([lon, lat]).addTo(map);
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
        if (typeof turf !== 'undefined' &&
            _driverRouteCoords &&
            _driverRouteCoords.length > 1 &&
            typeof _routeAnchorIdx === 'number' &&
            !isNaN(_routeAnchorIdx)) {

            var _i = Math.max(0, Math.min(_routeAnchorIdx, _driverRouteCoords.length - 2));
            var _curr = _driverRouteCoords[_i];
            var _next = _driverRouteCoords[_i + 1];

            if (_curr && _next) {
                var _routeBrg = turf.bearing(turf.point(_curr), turf.point(_next));
                _routeBrg = (_routeBrg + 360) % 360;

                // optional GPS assist at high speed
                if (lastHeading != null && spd > 15) {
                    var _diff = Math.abs(((_routeBrg - lastHeading + 540) % 360) - 180);
                    if (_diff < 20) _routeBrg = lastHeading;
                }

                brg = _routeBrg;
            }
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

        var interval;
        if (spd < 1.5) {
            interval = 999999;
        } else if (spd < 10) {
            interval = 150;
        } else {
            interval = 80;
        }
        var forceDisplay = false;
        if (_prevSpdForDisplay < 1.5 && spd >= 2.5) {
            forceDisplay = true;
        }
        _prevSpdForDisplay = spd;

        // _displayArrowBrg: displayBearing ni strelka uchun alohida smooth kuzatadi.
        // tau=0.06s — displayBearing (tau ~0.15-0.80s) dan tezroq,
        // shuning uchun kamera aylanayotganda strelka unga yopishib qoladi.
        if (_displayArrowBrg === null) _displayArrowBrg = displayBearing;
        var _arrowBrgShortcut = ((displayBearing - _displayArrowBrg + 540) % 360) - 180;
        _displayArrowBrg = (_displayArrowBrg + _arrowBrgShortcut * (1 - Math.exp(-dt / 0.06)) + 360) % 360;

        if (driverMarker && dLat !== null && dLng !== null) {
            if (forceDisplay || (_nowMs - _lastDisplayUpdate > interval)) {
                if (_dispLat === null || _dispLng === null) {
                    _dispLat = dLat;
                    _dispLng = dLng;
                }

                var alpha = (spd < 5) ? 0.15 : 0.25;

                _dispLat += (dLat - _dispLat) * alpha;
                _dispLng += (dLng - _dispLng) * alpha;

                driverMarker.setLngLat([_dispLng, _dispLat]);

                var _targetDeg = (displayHeading - _displayArrowBrg + 720) % 360;

                if (_dispArrowDeg === null) {
                    _dispArrowDeg = _targetDeg;
                }

                var delta = ((_targetDeg - _dispArrowDeg + 540) % 360) - 180;

                var alphaRot = (spd < 5) ? 0.15 : 0.25;

                _dispArrowDeg += delta * alphaRot;

                if (arrowEl) {
                    arrowEl.style.transform = 'rotate(' + _dispArrowDeg + 'deg)';
                }

                _lastDisplayUpdate = _nowMs;
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
            if ((_nowMs - _lastCamUpdate > 100) &&
                (_moved || _brgDelta > 2 || _zoomDelta > 0.1)) {
                map.easeTo({
                    center: [dLng, dLat],
                    bearing: displayBearing,
                    pitch: 60,
                    zoom: _zoom,
                    duration: 80,
                    easing: function(t){ return t * (2 - t); }
                });

                _lastCamLat = dLat;
                _lastCamLng = dLng;
                _lastCamUpdate = _nowMs;
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

    var driverLat = lat;
    var driverLng = lon;

    try {
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
    } catch (e) {
        var leMap = document.getElementById('loading');
        if (leMap) leMap.classList.add('hidden');
        showError("Xarita boshlanmadi.");
        return;
    }

    map.on('dragstart', function() { locked = false; });
    map.on('error', function() {
        var leErr = document.getElementById('loading');
        if (leErr) leErr.classList.add('hidden');
        showError("Xarita yuklanishda xatolik.");
    });
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
    if (d > MAX_DISTANCE_KM || d < 0 || isNaN(d)) { distEl.textContent = '0.00'; timeEl.textContent = '??'; return; }
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
    if (el) el.textContent = '??';
    el = document.getElementById('timeToClient');
    if (el) el.textContent = '??';
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
        // Route not loaded yet AND marker already created ??queue and wait.
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
        var _speedForFreeze = (lastGpsSpeedKmh != null && !isNaN(lastGpsSpeedKmh) && lastGpsSpeedKmh > 0)
            ? lastGpsSpeedKmh : spd;
        var _microMove = lastDriverLocation && lastDriverLocation.lat != null && lastDriverLocation.lon != null &&
            haversineM(lat, lng, lastDriverLocation.lat, lastDriverLocation.lon) < RAW_GPS_MIN_MOVE_M;
        var _freezeGpsRef = _microMove && _speedForFreeze < RAW_GPS_REF_FREEZE_MAX_KMH &&
            tLat != null && tLng != null && driverMarker;
        if (_freezeGpsRef) {
            sl = tLat;
            sa = tLng;
        } else if (typeof turf !== 'undefined' && _driverRouteLine && _driverRouteLine.geometry) {
            try {
                var _snapPt = turf.point([lng, lat]);
                var _lineDistM = turf.pointToLineDistance(_snapPt, _driverRouteLine, { units: 'meters' });
                var _snapRes = turf.nearestPointOnLine(_snapRouteLine || _driverRouteLine, _snapPt, { units: 'kilometers' });
                var _slNew = lat, _saNew = lng;
                if (_snapRes && _snapRes.geometry && _snapRes.geometry.coordinates) {
                    _saNew = _snapRes.geometry.coordinates[0];
                    _slNew = _snapRes.geometry.coordinates[1];
                }
                var _offRouteSnap = _lineDistM > ROUTE_SNAP_MAX_M;
                var _holdM = RAW_GPS_MIN_MOVE_M;
                if (_speedForFreeze >= 6) _holdM = 3;
                if (_speedForFreeze >= 12) _holdM = 2;
                var _onRouteHold = !_offRouteSnap && _prevSnappedLat != null && _prevSnappedLng != null &&
                    haversineM(_slNew, _saNew, _prevSnappedLat, _prevSnappedLng) < _holdM &&
                    _speedForFreeze < RAW_GPS_HOLD_MAX_KMH;
                if (_onRouteHold) {
                    sl = _prevSnappedLat;
                    sa = _prevSnappedLng;
                } else if (_snapRes && _snapRes.geometry && _snapRes.geometry.coordinates) {
                    sa = _saNew;
                    sl = _slNew;
                    // Turf returns the exact segment index ??use it directly.
                    // The old vertex-search loop found the nearest START node which is wrong
                    // when the projection point is near a segment's end (off-by-one ??wrong DR).
                    if (_snapRes.properties && _snapRes.properties.index != null) {
                        var _maxIdx = _driverRouteCoords.length > 1 ? _driverRouteCoords.length - 2 : 0;
                        var _newIdx = Math.min(_snapRes.properties.index, _maxIdx);
                        if (typeof _routeAnchorIdx === 'number' && !isNaN(_routeAnchorIdx) && _newIdx < _routeAnchorIdx) {
                            var diff = _routeAnchorIdx - _newIdx;

                            // Allow real backward jump if it's large (actual turn)
                            if (diff < 2) {
                                _newIdx = _routeAnchorIdx;
                            }
                        }

                        _routeAnchorIdx = _newIdx;
                        console.log('[ANCHOR UPDATE]', _routeAnchorIdx);
                        // Rebuild trimmed snap line: snapped point + all vertices ahead.
                        // Starting from the exact snapped coordinate (not segment start vertex)
                        // ensures the next snap cannot project backward even by one segment.
                        var _trimCoords = [[sa, sl]].concat(_driverRouteCoords.slice(_routeAnchorIdx + 1));
                        if (_trimCoords.length >= 2) {
                            try { _snapRouteLine = turf.lineString(_trimCoords); } catch (_) {}
                        }
                    }
                    _firstSnapDone = true;
                } else {
                    sl = _slNew;
                    sa = _saNew;
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
        // Adaptive dead zone: tezlikka qarab (2m..7m) GPS noise filtri
        // Bypassed on the first snap so a raw-GPS anchor can never be frozen onto
        // the route line ??prevTLat/Lng is guaranteed clean (on-route) from here on.
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
        if (!_freezeGpsRef) {
            lastDriverLocation = { lat: lat, lon: lng };
        }
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
        // Bearing: smooth blend between route-tangent (low speed) and coordinate
        // (high speed + sufficient movement). Replaces the hard 8 km/h cut.
        // _speedW: 0 at ?? km/h ??1 at ??5 km/h.
        // _distW:  0 at ?? m moved ??1 at ??0 m moved.
        // _coordW = _speedW 횞 _distW: BOTH conditions must be met for coordinate bearing.
        // Below 3 km/h the block is skipped entirely ??bearing is frozen.
        // updateDriverMarker must NOT modify brg (single source in renderLoop)
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
            // brg is owned by renderLoop (route-based single source)
        }
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
            map.flyTo({ center: [sa, sl], zoom: 18 });
            var pickLat = ORDER_DATA.pickup_latitude;
            var pickLon = ORDER_DATA.pickup_longitude;
            if (pickLat != null && pickLon != null) drawRoute(driverPos, { lat: pickLat, lng: pickLon });
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
        if (appState === 'trip' && !tripData.isWaiting) {
            if (tripData.lastPosition) {
                var segD = haversineM(
                    driverPos.lat, driverPos.lng,
                    tripData.lastPosition.lat, tripData.lastPosition.lng
                ) / 1000;
                // MICRO NOISE FILTER
                if (segD < 0.005) {
                } else {
                    // MAIN ACCUMULATION
                    if (segD > 0.007 && segD < 1) {
                        tripData.distance += segD;
                        tripData.lastPosition = driverPos;
                        updateTaximeter();
                        maybeSyncToServer();
                    }
                }
            } else {
                tripData.lastPosition = driverPos;
            }
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
        console.log('[ROUTE SETDATA]');
        map.getSource('route').setData(routeGeoJSON);
    } else {
        var addLayers = function() {
            if (map.getSource('route')) {
                console.log('[ROUTE SETDATA]');
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

function resetRouteProgress() {
    _lastProgressAnchorIdx = null;
}

function drawRoute(from, to) {
    if (!map || !from || !to) return Promise.resolve(false);
    if (_routeInFlight) return Promise.resolve(false);
    _routeInFlight = true;
    routeRoadDistanceKm = null;
    routeInstructions = [];
    routeCoordinates = [];
    _currentInstructionIndex = 0;

    // from: L.LatLng yoki {lat, lng} bo?쁫ishi mumkin
    var fromLat = from.lat != null ? from.lat : from[0];
    var fromLng = from.lng != null ? from.lng : from[1];
    var toLat = to.lat != null ? to.lat : to[0];
    var toLng = to.lng != null ? to.lng : to[1];

    var url = 'https://router.project-osrm.org/route/v1/driving/' +
        fromLng + ',' + fromLat + ';' + toLng + ',' + toLat +
        '?overview=full&geometries=geojson&steps=true';

    var controller = new AbortController();
    var timeoutId = setTimeout(function() { controller.abort(); }, 8000);

    var p = new Promise(function(resolve, reject) {
    fetch(url, { signal: controller.signal })
        .then(function(r) { return r.json(); })
        .then(function(data) {
            clearTimeout(timeoutId);
            if (!data || !data.routes || !data.routes.length) {
                fallbackStraightLine(fromLat, fromLng, toLat, toLng);
                resolve(true);
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
                resetRouteProgress();
            }
            if (!routeCoordinates.length) {
                fallbackStraightLine(fromLat, fromLng, toLat, toLng);
                resolve(true);
                return;
            }
            // Turf line feature qurish (snapping va progressive trim uchun)
            if (typeof turf !== 'undefined' && _driverRouteCoords.length >= 2) {
                try { _driverRouteLine = turf.lineString(_driverRouteCoords); } catch (_) {}
            }
            _snapRouteLine = _driverRouteLine;
            // RE-ANCHOR DRIVER TO NEW ROUTE (CRITICAL)
            if (typeof turf !== 'undefined' && _driverRouteLine && dLat !== null) {
                try {
                    var snap = turf.nearestPointOnLine(
                        _driverRouteLine,
                        turf.point([dLng, dLat])
                    );

                    if (snap && snap.geometry && snap.geometry.coordinates) {

                        var newLng = snap.geometry.coordinates[0];
                        var newLat = snap.geometry.coordinates[1];

                        // reset position to new route
                        tLat = newLat;
                        tLng = newLng;

                        dLat = newLat;
                        dLng = newLng;

                        // reset anchor for dead reckoning
                        _gpsAnchorLat = newLat;
                        _gpsAnchorLng = newLng;
                        _gpsAnchorMs = Date.now();

                        // reset prediction
                        _predLat = newLat;
                        _predLng = newLng;

                        // reset stop-mode
                        _lastStableLat = newLat;
                        _lastStableLng = newLng;

                        // reset heading
                        headingBuffer = [];

                        // reset progressive route baseline
                        _lastProgressLat = newLat;
                        _lastProgressLng = newLng;

                        // set correct anchor index
                        if (snap.properties && snap.properties.index != null) {
                            var _maxIdxRa = _driverRouteCoords.length > 1 ? _driverRouteCoords.length - 2 : 0;
                            _routeAnchorIdx = Math.min(snap.properties.index, _maxIdxRa);
                            console.log('[ANCHOR UPDATE]', _routeAnchorIdx);
                        }

                    }
                } catch (_) {}
            }
            // Replay any GPS update that arrived before the route was ready.
            if (_pendingGps !== null) {
                var _pg = _pendingGps; _pendingGps = null;
                updateDriverMarker(_pg.lat, _pg.lng, _pg.heading);
            }
            var routeGeoJSON = buildRouteGeoJSON(routeCoordinates);
            safeAddRouteLayer(routeGeoJSON);
            setTurnAndDistFromDriver({ lat: fromLat, lng: fromLng });
            updateNavUI();
            resolve(true);
        })
        .catch(function(err) {
            clearTimeout(timeoutId);
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

    var remainingCoords = _driverRouteCoords.slice(idx);
    if (!remainingCoords || remainingCoords.length < 2) return;

    // [lon,lat] -> [lat,lng] for buildRouteGeoJSON
    var trimCoords = remainingCoords.map(function(c) { return [c[1], c[0]]; });
    var geo = buildRouteGeoJSON(trimCoords);
    safeAddRouteLayer(geo);

    _lastProgressAnchorIdx = idx;
    _lastProgressLat = driverLat;
    _lastProgressLng = driverLon;
}

function fallbackStraightLine(fromLat, fromLng, toLat, toLng) {
    routeCoordinates = [[fromLat, fromLng], [toLat, toLng]];
    // Build _driverRouteLine so the queue gate is satisfied and snapping works
    // on the straight-line fallback exactly the same as on a real OSRM route.
    _driverRouteCoords = [[fromLng, fromLat], [toLng, toLat]];
    resetRouteProgress();
    if (typeof turf !== 'undefined' && _driverRouteCoords.length >= 2) {
        try { _driverRouteLine = turf.lineString(_driverRouteCoords); } catch (_) {}
    }
    _snapRouteLine = _driverRouteLine;
    routeRoadDistanceKm = haversineM(fromLat, fromLng, toLat, toLng) / 1000;
    routeInstructions = [{ text: "To'g'ri yo'l", type: -1, index: 0 }];
    _currentInstructionIndex = 0;
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
 * Uses turf.pointToLineDistance from the raw GPS fix to _driverRouteLine.
 * Requires two consecutive samples >= 30 m before tryReroute (reduces GPS spike false positives).
 * tryReroute applies cooldown, in-flight guard, then drawRoute.
 */
async function tryReroute(lat, lng) {
    var now = Date.now();
    if (now - _lastRerouteTime < 5000) return false;
    if (_rerouteInFlight) return false;
    if (_routeInFlight) return false;

    _rerouteInFlight = true;
    _lastRerouteTime = now;

    try {
        _firstSnapDone = false;
        _routeAnchorIdx = 0;
        resetRouteProgress();
        console.log('[ANCHOR UPDATE]', _routeAnchorIdx);
        _snapRouteLine = null;
        var routed = await drawRoute(
            { lat: lat, lng: lng },
            {
                lat: ORDER_DATA.destination_latitude,
                lng: ORDER_DATA.destination_longitude
            }
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
        if (distM >= 30) {
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
    var coords = [
        [fromLat, fromLng],
        [toLat, toLng]
    ];
    var routeGeoJSON = buildRouteGeoJSON(coords);
    safeAddRouteABLayer(routeGeoJSON);
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
            fetch(API_BASE_URL + '/api/webapp/order/' + oid + '/trip/resume?v=' + Date.now(), {
                method: 'POST',
                headers: webappHeaders()
            }).catch(function() {});
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
    var fareEl = document.getElementById('currentFare');
    if (!fareEl) { safeAlert("UI topilmadi."); return; }
    var finalFare = fareEl.textContent.replace(/,/g, '');
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

/** Tiered waiting fee (so'm) — keep in sync with server compute_waiting_fee. */
function calculateWaitingFee(waitingSeconds) {
    if (!waitingSeconds || waitingSeconds <= 0) return 0;
    var minutes = Math.ceil(waitingSeconds / 60);
    return 1000 + Math.max(0, minutes - 1) * 500;
}

function updateTaximeter() {
    var surge = tripData.surge != null && !isNaN(Number(tripData.surge)) ? Number(tripData.surge) : 1;
    var distancePart = tripData.distance * TARIFF.pricePerKm;
    var surgedDistance = distancePart * surge;
    var distanceFare = TARIFF.startPrice + surgedDistance;
    var waitingFee = calculateWaitingFee(tripData.waitingTime);
    var uiFare = distanceFare + waitingFee;
    if (!tripData.isWaiting && tripData.serverFare != null) {
        if (Math.abs(tripData.serverFare - uiFare) > 100) {
            uiFare = tripData.serverFare;
        }
    }
    var rounded = Math.round(uiFare / 100) * 100;
    var curFareEl = document.getElementById('currentFare');
    var tripDistEl = document.getElementById('tripDistance');
    if (curFareEl) curFareEl.textContent = rounded.toLocaleString('en-US');
    if (tripDistEl) tripDistEl.textContent = tripData.distance.toFixed(2);
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
        if (map) map.resize();
        updateSyncUI();
        flushPendingTrips();
        if (appState === 'trip') {
            enableWakeLock();
        }
    }
});
window.addEventListener('resize', function() {
    if (map) map.resize();
});

window.onload = init;
