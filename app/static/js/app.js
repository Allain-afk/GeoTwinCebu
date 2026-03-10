/* ── Global state ─────────────────────────────────────────────────── */
let map, basemapLayers = {}, overlayLayers = {}, centerMarkers;
let userMarker = null, routeLayer = null;
let userLat = null, userLon = null;
let metadata = null;
let drawerOpen = false;
let currentRouteData = null;

/* ── Helpers ──────────────────────────────────────────────────────── */
function $(id) { return document.getElementById(id); }

function setStatus(msg, type = "muted") {
  $("statusMsg").innerHTML = msg;
  $("statusMsg").className = `text-${type}`;
}

/* ── Mobile drawer toggle ────────────────────────────────────────── */
function toggleDrawer(forceOpen) {
  const sidebar = $("sidebar");
  const fab = $("mobileFab");
  const isMobile = window.innerWidth < 768;
  if (!isMobile) return;

  drawerOpen = (forceOpen !== undefined) ? forceOpen : !drawerOpen;
  sidebar.classList.toggle("drawer-open", drawerOpen);
  if (fab) fab.classList.toggle("hidden", drawerOpen);
}

/* ── Icon helpers ─────────────────────────────────────────────────── */
const CENTER_TYPE = {
  school:        { icon: "🏫", color: "#16a34a" },
  gymnasium:     { icon: "🏟️", color: "#2563eb" },
  barangay_hall: { icon: "🏛️", color: "#7c3aed" },
  hospital:      { icon: "🏥", color: "#dc2626" },
};
function makeCenterIcon(type) {
  const t = CENTER_TYPE[type] || { icon: "📍", color: "#2563eb" };
  return L.divIcon({
    className: "",
    html: `<div style="background:${t.color};color:#fff;border-radius:50%;width:32px;height:32px;display:flex;align-items:center;justify-content:center;font-size:16px;box-shadow:0 2px 8px rgba(0,0,0,.25);border:2px solid #fff;">${t.icon}</div>`,
    iconSize: [32, 32], iconAnchor: [16, 16], popupAnchor: [0, -18],
  });
}
function makeUserIcon() {
  return L.divIcon({
    className: "",
    html: `<div style="background:#ef4444;color:#fff;border-radius:50%;width:28px;height:28px;display:flex;align-items:center;justify-content:center;font-size:15px;box-shadow:0 2px 8px rgba(0,0,0,.3);border:2px solid #fff;">📌</div>`,
    iconSize: [28, 28], iconAnchor: [14, 28], popupAnchor: [0, -30],
  });
}

/* ── Map init ─────────────────────────────────────────────────────── */
function initMap() {
  map = L.map("map", { zoomControl: true }).setView([10.3157, 123.8854], 13);
  centerMarkers = L.layerGroup().addTo(map);
  map.on("click", e => {
    setUserPin(e.latlng.lat, e.latlng.lng, "map-click");
    // On mobile, open drawer so user sees the result
    toggleDrawer(true);
  });
}

function initBasemaps() {
  const sel = $("basemapSelect");
  sel.innerHTML = "";
  metadata.basemaps.forEach((bm, i) => {
    const opt = document.createElement("option");
    opt.value = bm.id; opt.textContent = bm.name;
    sel.appendChild(opt);
    basemapLayers[bm.id] = L.tileLayer(bm.url, { maxZoom: 20, attribution: bm.attribution });
  });
  basemapLayers[metadata.basemaps[0].id].addTo(map);
  sel.addEventListener("change", () => {
    Object.values(basemapLayers).forEach(l => map.removeLayer(l));
    basemapLayers[sel.value].addTo(map);
  });
}

function initHazardLayersPanel() {
  const panel = $("hazardLayersPanel");
  panel.innerHTML = "";
  Object.keys(metadata.layers).forEach(lid => {
    const layer = metadata.layers[lid];
    const color = layer.style?.color || "#888";
    const row = document.createElement("div");
    row.className = "hazard-item";
    row.innerHTML = `
      <div class="hazard-swatch" style="background:${color};opacity:.75;"></div>
      <span style="flex:1;">${layer.title}</span>
      <div class="form-check form-switch mb-0">
        <input class="form-check-input" type="checkbox" role="switch" id="layer_${lid}">
      </div>`;
    panel.appendChild(row);
    row.querySelector(`#layer_${lid}`).addEventListener("change", e => {
      toggleHazardLayer(lid, e.target.checked);
    });
  });
}

/* ── Evacuation centers ───────────────────────────────────────────── */
async function loadEvacuationCenters() {
  try {
    const fc = await fetch("/api/evacuation-centers").then(r => r.json());
    centerMarkers.clearLayers();
    fc.features.forEach(feat => {
      const [lon, lat] = feat.geometry.coordinates;
      const p = feat.properties;
      const t = CENTER_TYPE[p.type] || { icon: "📍" };
      L.marker([lat, lon], { icon: makeCenterIcon(p.type) })
        .bindPopup(`
          <div class="popup-name">${p.name}</div>
          <span class="popup-type">${t.icon} ${p.type.replace("_", " ")}</span><br>
          <div class="popup-cap">📍 ${p.barangay || ""}</div>
          ${p.capacity ? `<div class="popup-cap">👥 Capacity: ~${p.capacity.toLocaleString()}</div>` : ""}
          ${p.notes ? `<div class="popup-cap">ℹ️ ${p.notes}</div>` : ""}
        `)
        .addTo(centerMarkers);
    });
  } catch (e) { console.warn("Could not load centers:", e); }
}

/* ── Hazard layer toggles ─────────────────────────────────────────── */
async function toggleHazardLayer(lid, checked) {
  if (!checked) {
    if (overlayLayers[lid]) { map.removeLayer(overlayLayers[lid]); delete overlayLayers[lid]; }
    return;
  }
  setStatus(`<span class="spinner-sm"></span> Loading ${metadata.layers[lid].title}…`);
  try {
    const b = map.getBounds();
    const bbox = [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()];
    const data = await fetch("/api/layer-geojson", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ layer_id: lid, bbox }),
    }).then(r => r.json());
    if (!data.ok) { setStatus(`Layer error: ${data.error}`, "danger"); return; }
    overlayLayers[lid] = L.geoJSON(data.geojson, { style: () => metadata.layers[lid].style || {} }).addTo(map);
    setStatus("Layer loaded.", "success");
  } catch (e) { setStatus("Layer fetch error: " + e, "danger"); }
}

/* ── User pin ─────────────────────────────────────────────────────── */
function setUserPin(lat, lon, source = "manual") {
  userLat = lat; userLon = lon;
  if (userMarker) map.removeLayer(userMarker);
  userMarker = L.marker([lat, lon], { icon: makeUserIcon() })
    .bindPopup(`<b>Your location</b><br>${lat.toFixed(5)}, ${lon.toFixed(5)}`)
    .addTo(map);
  const latEl = $("latInput"), lonEl = $("lonInput");
  if (latEl) latEl.value = lat.toFixed(5);
  if (lonEl) lonEl.value = lon.toFixed(5);
  if (source !== "coords") map.setView([lat, lon], Math.max(map.getZoom(), 14));
  setStatus("📌 Location set — tap <b>Find Evacuation Center</b> below.", "success");
}

/* ── GPS ──────────────────────────────────────────────────────────── */
function pinMyLocation() {
  if (!navigator.geolocation) { setStatus("GPS not available in this browser.", "danger"); return; }
  setStatus(`<span class="spinner-sm"></span> Getting your GPS location…`);
  navigator.geolocation.getCurrentPosition(
    pos => {
      toggleDrawer(false); // collapse drawer so map is visible
      setUserPin(pos.coords.latitude, pos.coords.longitude, "gps");
      $("useMyLocationBtn").classList.add("active");
    },
    () => setStatus("Could not get GPS. Tap the map or enter coordinates.", "danger"),
    { enableHighAccuracy: true, timeout: 10000 }
  );
}

/* ── Manual coordinate input ──────────────────────────────────────── */
function pinCoordinates() {
  const lat = parseFloat($("latInput").value);
  const lon = parseFloat($("lonInput").value);
  if (isNaN(lat) || isNaN(lon)) { setStatus("Please enter valid latitude and longitude.", "danger"); return; }
  toggleDrawer(false);
  setUserPin(lat, lon, "coords");
}

/* ── Parse boundary (advanced) ────────────────────────────────────── */
async function parseBoundary() {
  setStatus(`<span class="spinner-sm"></span> Parsing boundary…`);
  try {
    const data = await fetch("/api/parse-boundary", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode: $("manualType").value, crs: ($("manualCrs").value || "EPSG:4326").trim(), text: $("manualText").value }),
    }).then(r => r.json());
    if (!data.ok) { setStatus(data.error || "Parse failed.", "danger"); return; }
    const coords = data.geometry.coordinates[0];
    const lat = coords.reduce((s, c) => s + c[1], 0) / coords.length;
    const lon = coords.reduce((s, c) => s + c[0], 0) / coords.length;
    toggleDrawer(false);
    setUserPin(lat, lon, "parse");
    const qa = data.qa || {};
    $("qaBox").textContent = `Area: ${(qa.area_m2 / 10000).toFixed(3)} ha | Perimeter: ${qa.perimeter_m} m` +
      ((qa.warnings || []).length ? " | ⚠️ " + qa.warnings.join(" | ") : "");
    setStatus("Boundary parsed ✓", "success");
  } catch (e) { setStatus("Error: " + e, "danger"); }
}

/* ── Find route ───────────────────────────────────────────────────── */
async function findRoute() {
  if (userLat === null) {
    setStatus("Please set your location first.", "danger");
    toggleDrawer(true);
    return;
  }
  $("findRouteBtn").disabled = true;
  if ($("mobileFab")) $("mobileFab").disabled = true;
  $("resultsPanel").style.display = "none";
  setStatus(`<span class="spinner-sm"></span> Finding nearest evacuation center…`);
  toggleDrawer(true);

  const active_layers = Object.keys(metadata.layers).filter(lid => document.getElementById(`layer_${lid}`)?.checked);

  try {
    const data = await fetch("/api/route", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ lat: userLat, lon: userLon, active_layers }),
    }).then(r => r.json());

    if (!data.ok) { setStatus(data.error || "Routing failed.", "danger"); return; }
    currentRouteData = data;
    renderResults(data);
    renderRouteOnMap(data);
    setStatus("Route found ✓", "success");
  } catch (e) {
    setStatus("Error: " + e, "danger");
  } finally {
    $("findRouteBtn").disabled = false;
    if ($("mobileFab")) $("mobileFab").disabled = false;
  }
}

/* ── Render results ───────────────────────────────────────────────── */
function renderResults(data) {
  const warnEl = $("hazardWarnings");
  if (data.hazard_warnings?.length) {
    warnEl.innerHTML = data.hazard_warnings.map(w => `<div class="hazard-warning">${w}</div>`).join("");
  } else {
    warnEl.innerHTML = `<div class="hazard-safe">✅ No immediate hazard detected at your location based on available data.</div>`;
  }

  const typeMap = { school: "School / University", gymnasium: "Gymnasium / Arena", barangay_hall: "Barangay Hall", hospital: "Hospital" };
  const srcNote = data.route_source === "straight_line"
    ? `<div class="route-src-note">⚠️ Showing straight-line estimate — road data unavailable. Use Google Maps for actual directions.</div>` : "";

  $("primaryResult").innerHTML = `
    <div class="center-name">🏳️ ${data.center.name}</div>
    <div class="center-meta">
      ${typeMap[data.center.type] || data.center.type} · ${data.center.barangay}
      ${data.center.capacity ? ` · ~${data.center.capacity.toLocaleString()} capacity` : ""}
    </div>
    ${data.center.notes ? `<div class="center-meta">ℹ️ ${data.center.notes}</div>` : ""}
    <div class="route-stats">
      <div class="stat-box"><div class="stat-label">Distance</div><div class="stat-value">${data.distance_label}</div></div>
      <div class="stat-box"><div class="stat-label">Est. Travel Time</div><div class="stat-value">${data.duration_label}</div></div>
    </div>
    ${srcNote}
    <a class="gmaps-btn mt-2" href="${data.google_maps_url}" target="_blank" rel="noopener">
      <svg width="16" height="16" viewBox="0 0 48 48" fill="none"><circle cx="24" cy="24" r="24" fill="white"/><path d="M24 12C18.477 12 14 16.477 14 22C14 29.5 24 38 24 38S34 29.5 34 22C34 16.477 29.523 12 24 12ZM24 27C21.239 27 19 24.761 19 22S21.239 17 24 17 29 19.239 29 22 26.761 27 24 27Z" fill="#4285F4"/></svg>
      Open in Google Maps
    </a>`;

  const altSec = $("alternativesSection");
  const icons = { school: "🏫", gymnasium: "🏟️", barangay_hall: "🏛️", hospital: "🏥" };
  altSec.innerHTML = data.alternatives?.length
    ? `<div class="alt-title">Other Nearby Centers</div>` + data.alternatives.map(a => `
        <div class="alt-item">
          <span class="alt-icon">${icons[a.type] || "📍"}</span>
          <div><div class="alt-name">${a.name}</div><div class="alt-dist">${a.barangay} · ${a.distance_label} away</div></div>
        </div>`).join("")
    : "";

  $("resultsPanel").style.display = "block";
}

/* ── Render route on map ──────────────────────────────────────────── */
function renderRouteOnMap(data) {
  if (routeLayer) map.removeLayer(routeLayer);
  routeLayer = L.geoJSON(data.route, {
    style: { color: "#2563eb", weight: 5, opacity: .85, dashArray: data.route_source === "straight_line" ? "8 6" : null },
  }).addTo(map);
  L.marker([data.center.lat, data.center.lon], { icon: makeCenterIcon(data.center.type) })
    .bindPopup(`<div class="popup-name">🏳️ ${data.center.name}</div><div class="popup-cap">Nearest evacuation center</div>`)
    .addTo(routeLayer);
  const bounds = routeLayer.getBounds();
  if (bounds.isValid()) map.fitBounds(bounds.pad(0.15));
}

/* ── Download PDF Report ──────────────────────────────────────────── */
async function downloadPdfReport() {
  const btn = $("downloadPdfBtn");
  if (btn) btn.disabled = true;
  setStatus("<span class=\"spinner-sm\"></span> Capturing map…");
  let mapImageBase64 = null;
  try {
    if (typeof html2canvas === "function") {
      const canvas = await html2canvas($("map"), { useCORS: true });
      const dataUrl = canvas.toDataURL("image/png");
      mapImageBase64 = dataUrl.replace(/^data:image\/png;base64,/, "");
    }
  } catch (e) {
    console.warn("Map capture failed:", e);
  }
  setStatus("<span class=\"spinner-sm\"></span> Generating report…");

  const b = map.getBounds();
  const bbox = [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()];
  const activeLayers = Object.keys(metadata.layers).filter(lid => document.getElementById(`layer_${lid}`)?.checked);

  const routeInfo = {};
  if (userLat != null && userLon != null) {
    routeInfo.origin_lat = userLat;
    routeInfo.origin_lon = userLon;
  }
  if (currentRouteData?.center) {
    routeInfo.dest_lat = currentRouteData.center.lat;
    routeInfo.dest_lon = currentRouteData.center.lon;
    routeInfo.dest_name = currentRouteData.center.name;
  }
  if (currentRouteData?.duration_label) routeInfo.duration_text = currentRouteData.duration_label;
  if (currentRouteData?.distance_label) routeInfo.distance_text = currentRouteData.distance_label;

  const payload = {
    aoi: { bbox },
    active_layers: activeLayers,
    map_image: mapImageBase64,
    route_info: Object.keys(routeInfo).length ? routeInfo : undefined,
  };

  try {
    const res = await fetch("/api/report-pdf", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      setStatus("Report failed: " + (err.error || res.status), "danger");
      return;
    }
    const blob = await res.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "geotwin_report.pdf";
    a.click();
    URL.revokeObjectURL(a.href);
    setStatus("PDF downloaded ✓", "success");
  } catch (e) {
    setStatus("Error: " + e.message, "danger");
  } finally {
    if (btn) btn.disabled = false;
  }
}

/* ── Bootstrap ────────────────────────────────────────────────────── */
document.addEventListener("DOMContentLoaded", async () => {
  metadata = await fetch("/api/metadata").then(r => r.json());
  initMap();
  initBasemaps();
  initHazardLayersPanel();
  loadEvacuationCenters();

  [$("latInput"), $("lonInput")].forEach(el => {
    el?.addEventListener("keydown", e => { if (e.key === "Enter") pinCoordinates(); });
  });

  // Swipe-up gesture on drawer handle
  let touchStartY = 0;
  $("drawerHandle")?.addEventListener("touchstart", e => { touchStartY = e.touches[0].clientY; }, { passive: true });
  $("drawerHandle")?.addEventListener("touchend", e => {
    const dy = touchStartY - e.changedTouches[0].clientY;
    if (Math.abs(dy) > 30) toggleDrawer(dy > 0); // swipe up = open, swipe down = close
  });
});
