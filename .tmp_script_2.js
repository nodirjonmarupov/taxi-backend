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
        let TARIFF = { startPrice: 5000, pricePerKm: 2500, pricePerMinWaiting: 500, minDistanceUpdate: 0.005 };
        let ORDER_DATA = null;
        const tg = (window.Telegram && window.Telegram.WebApp) ? window.Telegram.WebApp : { expand: function(){}, ready: function(){} };

        let map, tileLayer, driverMarker, clientMarker, destMarker, routeControl, routeControlAB;
        let routeRoadDistanceKm = null;
        let routeInstructions = [], routeCoordinates = [], routePolyline = null, routeDecorator = null;
        let map2dMode = true;
        let arrowEl = null;
        let tLat = null, tLng = null, dLat = null, dLng = null, brg = 0, spd = 0;
        let pLat = null, pLng = null, locked = true, lastCam = 0;
        let simIdx = 0, simOn = false, simTmr = null, turnI = 0, distKm = 1;
        let displayBearing = 0, targetBearing = 0;
        let headingBuffer = [];
        const SPEED_THRESHOLD_KMH = 5;
        const HEADING_CHANGE_THRESHOLD = 8;
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
            .then(function(d){ TARIFF.startPrice = d.startPrice||5000; TARIFF.pricePerKm = d.pricePerKm||2500; TARIFF.pricePerMinWaiting = d.pricePerMinWaiting||500; TARIFF.minDistanceUpdate = d.minDistanceUpdate||0.005; })
            .catch(function(){});
        const urlParams = new URLSearchParams(window.location.search);
        const ORDER_ID_CURRENT = urlParams.get('order_id');
        if (ORDER_ID_CURRENT) console.log("Joriy buyurtma ID:", ORDER_ID_CURRENT);
        const MAX_DISTANCE_KM = 500;

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
        function snapToRoute(lat, lng) {
            var coords = routeCoordinates;
            if (!coords || coords.length < 2) return [lat, lng];
            var toLL = function(c) { return c && (c.lat != null) ? [c.lat, c.lng] : (Array.isArray(c) ? c : [c[0], c[1]]); };
            var best = null, bd = Infinity;
            for (var i = 0; i < coords.length - 1; i++) {
                var p1 = toLL(coords[i]), p2 = toLL(coords[i + 1]);
                var y1 = p1[0], x1 = p1[1], y2 = p2[0], x2 = p2[1];
                var dy = y2 - y1, dx = x2 - x1, l2 = dy * dy + dx * dx;
                if (!l2) continue;
                var t = Math.max(0, Math.min(1, ((lat - y1) * dy + (lng - x1) * dx) / l2));
                var d = Math.hypot(lat - y1 - t * dy, lng - x1 - t * dx);
                if (d < bd) { bd = d; best = [y1 + t * dy, x1 + t * dx]; }
            }
            return (best && bd < 0.005) ? best : [lat, lng];
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
            var ring = document.createElement('div');
            ring.className = 'dm-ring';
            var circle = document.createElement('div');
            circle.className = 'dm-circle';
            var svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
            svg.setAttribute('viewBox', '0 0 24 24');
            svg.setAttribute('class', 'dm-arrow');
            svg.innerHTML = '<path d="M12 2L4.5 20.29l.71.71L12 18l6.79 3 .71-.71z"/>';
            arrowEl = svg;
            circle.appendChild(svg);
            wrap.appendChild(ring);
            wrap.appendChild(circle);
            driverMarker = new maplibregl.Marker({
                element: wrap,
                anchor: 'center',
                rotationAlignment: 'map',
                pitchAlignment: 'viewport'
            }).setLngLat([lon, lat]).addTo(map);
        }
        function followCam() {
            if (!locked || !map || dLat == null || dLng == null) return;
            var zoom = speedToZoom(spd);
            var H = window.innerHeight;
            map.easeTo({
                center: [dLng, dLat],
                bearing: displayBearing,
                pitch: 60,
                zoom: zoom,
                padding: {
                    top: 80,
                    bottom: Math.round(H * 0.45),
                    left: 0,
                    right: 0
                },
                duration: 250,
                easing: function(t) { return t < 0.5 ? 2*t*t : -1+(4-2*t)*t; }
            });
        }
        function recenter() {
            locked = true;
            if (dLat != null && dLng != null && map) {
                var H = window.innerHeight;
                map.easeTo({
                    center: [dLng, dLat],
                    bearing: displayBearing,
                    pitch: 55,
                    zoom: speedToZoom(spd),
                    padding: { top: 0, bottom: Math.round(H * 0.30), left: 0, right: 0 },
                    duration: 300
                });
            } else if (lastDriverLocation && map) {
                map.easeTo({
                    center: [lastDriverLocation.lon, lastDriverLocation.lat],
                    zoom: map.getZoom() || 17,
                    bearing: displayBearing,
                    pitch: 55,
                    duration: 300
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

                // Smooth position interpolation
                if (tLat != null && tLng != null && dLat != null && dLng != null) {
                    var posAlpha = 1 - Math.pow(0.001, dt * 7);
                    dLat = lerp(dLat, tLat, posAlpha);
                    dLng = lerp(dLng, tLng, posAlpha);
                }

                // Smooth bearing
                if (!useManualBearing) targetBearing = northUpMode ? 0 : brg;
                var rotAlpha = 1 - Math.pow(0.001, dt * 1.8);
                displayBearing = lerpAngle(displayBearing, targetBearing, rotAlpha);

                // Rotate driver arrow (counter-rotate so it always points up)
                if (arrowEl) arrowEl.style.transform = 'rotate(' + displayBearing + 'deg)';

                // Update driver marker position
                if (driverMarker && dLat != null && dLng != null) {
                    driverMarker.setLngLat([dLng, dLat]);
                }

                // Camera follow with MapLibre native bearing + pitch
                if (locked && dLat != null && dLng != null) {
                    var now = Date.now();
                    if (now - lastCam > 150) {
                        lastCam = now;
                        var zoom = speedToZoom(spd);
                        var H = window.innerHeight;
                        map.easeTo({
                            center: [dLng, dLat],
                            bearing: displayBearing,
                            pitch: 60,
                            zoom: zoom,
                            padding: {
                                top: 80,
                                bottom: Math.round(H * 0.45),
                                left: 0,
                                right: 0
                            },
                            duration: 250,
                            easing: function(t) { return t < 0.5 ? 2*t*t : -1+(4-2*t)*t; }
                        });
                    }
                }

                renderLoop();
            });
        }
        function updateNavUI() {
            var distM = distKm >= 1 ? (distKm.toFixed(1) + 'km') : (Math.round(distKm * 1000) + 'm');
            var inst = routeInstructions[turnI] || routeInstructions[0];
            var street = inst && inst.text ? inst.text : "Mijozga yo\u0027l";
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
                const response = await fetch(API_BASE_URL + '/api/webapp/order/' + orderId + '?v=' + Date.now(), {
                    headers: { "ngrok-skip-browser-warning": "true" }
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
                    showError("Mijoz joylashuvi noto\u0027g\u0027ri.");
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
            var arriving = document.getElementById('arrivingPanel');
            if (arriving) arriving.style.display = 'none';

            var isCompleted = (status === 'completed');
            var icon = isCompleted ? '✅' : '❌';
            var msg = isCompleted ? '✅ Safar yakunlangan' : '❌ Buyurtma bekor qilingan';

            var html = ''
                + '<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;'
                + 'height:100vh;background:#000;color:#fff;text-align:center;padding:32px;gap:20px;">'
                +   '<div style="font-size:64px;">' + icon + '</div>'
                +   '<div style="font-size:24px;font-weight:700;">' + msg + '</div>'
                +   '<div style="font-size:15px;color:rgba(255,255,255,0.6);">'
                +     'Bu buyurtma allaqachon yakunlangan.'
                +   '</div>'
                +   '<button onclick="if(window.Telegram&&window.Telegram.WebApp){Telegram.WebApp.close()}" '
                +     'style="margin-top:16px;padding:16px 32px;background:#276EF1;color:#fff;'
                +     'border:none;border-radius:16px;font-size:16px;font-weight:700;cursor:pointer;">'
                +     'Yopish'
                +   '</button>'
                + '</div>';

            document.body.innerHTML = html;
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
            fetch(API_BASE_URL + '/api/webapp/update_driver_location?v=' + Date.now(), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'ngrok-skip-browser-warning': 'true' },
                body: JSON.stringify({ driver_id: ORDER_DATA.driver_id, latitude: lat, longitude: lng, heading: heading })
            }).then(function(){}).catch(function(){});
        }
        function startDriverTracking() {
            if (intervals.position != null) return;
            var opts = { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 };

            /* Try Telegram LocationManager first (no popup) */
            var tgApp = window.Telegram && window.Telegram.WebApp;
            if (tgApp && tgApp.LocationManager) {
                try {
                    tgApp.LocationManager.init(function() {
                        if (tgApp.LocationManager.isLocationAvailable) {
                            intervals.position = setInterval(function() {
                                tgApp.LocationManager.getLocation(function(loc) {
                                    if (!loc) return;
                                    var lat = loc.latitude, lng = loc.longitude;
                                    var heading = loc.course != null ? loc.course : null;
                                    var sp = loc.speed != null ? loc.speed * 3.6 : null;
                                    if (sp != null) lastGpsSpeedKmh = sp;
                                    updateDriverMarker(lat, lng, heading || lastHeading);
                                    sendDriverLocationToBackend(lat, lng, heading || lastHeading);
                                });
                            }, 2000);
                            return;
                        }
                        /* fallback to navigator.geolocation */
                        _startBrowserGPS(opts);
                    });
                    return;
                } catch (e) {}
            }

            /* Fallback: browser geolocation */
            _startBrowserGPS(opts);
        }

        function _startBrowserGPS(opts) {
            if (!navigator.geolocation) {
                showGpsError("GPS ishlamayapti!");
                return;
            }
            navigator.geolocation.getCurrentPosition(
                function(position) {
                    var lat = position.coords.latitude;
                    var lng = position.coords.longitude;
                    var sp = position.coords.speed;
                    if (sp != null && !isNaN(sp)) lastGpsSpeedKmh = sp * 3.6;
                    lastDriverLocation = { lat: lat, lon: lng };
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
                        opts
                    );
                },
                function(error) { onGeoError(error); },
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
                if (heading == null || isNaN(heading)) heading = lastHeading;
                lastHeading = heading;
                var driverPos = { lat: lat, lng: lng };
                var now = Date.now();
                var speedKmh = 0;
                if (lastDriverLocation && lastPositionTime) {
                    var distM = haversineM(driverPos.lat, driverPos.lng, lastDriverLocation.lat, lastDriverLocation.lon);
                    var dtSec = (now - lastPositionTime) / 1000;
                    if (dtSec > 0) speedKmh = (distM / 1000) / dtSec * 3600;
                }
                if (lastGpsSpeedKmh != null && !isNaN(lastGpsSpeedKmh) && lastGpsSpeedKmh > 0) speedKmh = lastGpsSpeedKmh;
                lastPositionTime = now;
                lastDriverLocation = { lat: lat, lon: lng };
                var sl = lat, sa = lng;
                if (routeCoordinates.length >= 2) {
                    var snap = snapToRoute(lat, lng);
                    sl = snap[0];
                    sa = snap[1];
                }
                pLat = lat;
                pLng = lng;
                tLat = sl;
                tLng = sa;
                spd = speedKmh;
                if (heading != null && !isNaN(heading)) {
                    headingBuffer.push(heading);
                    if (headingBuffer.length > 5) headingBuffer.shift();
                    var smoothHeading = circularMeanHeadings(headingBuffer);
                    if (speedKmh > SPEED_THRESHOLD_KMH) {
                        var diff = Math.abs(((smoothHeading - targetBearing + 540) % 360) - 180);
                        if (diff >= HEADING_CHANGE_THRESHOLD) brg = smoothHeading;
                    }
                }
                if (!driverMarker) {
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
                        var segD = haversineM(driverPos.lat, driverPos.lng, tripData.lastPosition.lat, tripData.lastPosition.lng) / 1000;
                        if (segD >= TARIFF.minDistanceUpdate && segD < 1) { tripData.distance += segD; updateTaximeter(); }
                    }
                    tripData.lastPosition = driverPos;
                }
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

            fetch(url)
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (!data || !data.routes || !data.routes.length) return;
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
                    }
                    if (!routeCoordinates.length) return;

                    var routeGeoJSON = buildRouteGeoJSON(routeCoordinates);
                    safeAddRouteLayer(routeGeoJSON);
                    setTurnAndDistFromDriver({ lat: fromLat, lng: fromLng });
                    updateNavUI();
                })
                .catch(function() {});
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
                var resp = await fetch(
                    API_BASE_URL + '/api/webapp/order/' + ORDER_ID_CURRENT + '/arrived?v=' + Date.now(),
                    {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'ngrok-skip-browser-warning': 'true'
                        }
                    }
                );
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

        function handleStartTrip() {
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
                return;
            }
            appState = 'trip';
            document.getElementById('arrivingPanel').style.display = 'none';
            document.getElementById('taximeterScreen').classList.add('active');
            document.getElementById('map').classList.add('minimized');
            var nav = ['top-bar','nav-bottom'];
            for (var i = 0; i < nav.length; i++) { var el = document.getElementById(nav[i]); if (el) el.style.display = 'none'; }
            var pos = driverMarker.getLngLat();
            tripData.lastPosition = { lat: pos.lat, lng: pos.lng };
            intervals.timer = setInterval(updateTimer, 1000);
            updateTaximeter();
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
            safeConfirm("Safarni yakunlab, to\u0027lovni oldingizmi?", finishTrip);
        }

        async function finishTrip() {
            var orderId = ORDER_ID_CURRENT;
            if (!orderId) { safeAlert("Order ID topilmadi."); return; }
            var finalFare = document.getElementById('currentFare').textContent.replace(/,/g, '');
            var distKm = tripData.distance;
            var params = new URLSearchParams({ new_status: 'completed' });
            if (distKm != null && !isNaN(distKm)) params.set('distance_km', String(distKm));
            if (finalFare && !isNaN(parseFloat(finalFare))) params.set('final_price', finalFare);
            document.getElementById('loading').classList.remove('hidden');

            try {
                var qs = params.toString();
                var response = await fetch(API_BASE_URL + '/api/webapp/order/' + orderId + '/status?' + qs + '&v=' + Date.now(), {
                    method: 'POST',
                    headers: { "ngrok-skip-browser-warning": "true" }
                });

                if (response.ok) {
                    clearInterval(intervals.timer);
                    if (ORDER_DATA) ORDER_DATA.status = 'completed';
                    document.getElementById('loading').classList.add('hidden');

                    var payload = { status: "finished", order_id: parseInt(orderId, 10), final_price: parseFloat(finalFare) || 0, distance_km: distKm || 0 };

                    if (tg && tg.showAlert) {
                        tg.showAlert(
                            "Safar yakunlandi!\nTo'lov: " + finalFare + " so'm",
                            function() {
                                if (tg && tg.sendData) tg.sendData(JSON.stringify(payload));
                                if (tg && tg.close) tg.close();
                            }
                        );
                    } else {
                        if (tg && tg.sendData) tg.sendData(JSON.stringify(payload));
                        if (tg && tg.close) tg.close();
                    }
                } else {
                    document.getElementById('loading').classList.add('hidden');
                    var errText = "Statusni yangilab bo\u0027lmadi";
                    try { var j = await response.json(); if (j && j.detail) errText = j.detail; } catch (_) {}
                    safeAlert("Xato: " + errText);
                }
            } catch (e) {
                document.getElementById('loading').classList.add('hidden');
                safeAlert("Serverga ulanishda xatolik. Internetni tekshiring.");
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

        window.onload = init;
    