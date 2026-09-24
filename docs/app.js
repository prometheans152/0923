/**
 * Taiwan CWA Real-time Weather Map Dashboard
 * Combines AirBox dense station spatial visualization with Taiwan Weather Map meteorological clarity.
 */

// Global State
const state = {
  data: null,
  stations: [],
  filteredStations: [],
  selectedStation: null,
  map: null,
  markerLayer: null,
  markersMap: new Map(), // station_id -> L.marker
  currentTileLayer: null,
  isDarkTheme: true,
  autoRefreshInterval: null,
  countdownSeconds: 300,
  countdownInterval: null,
  // 7-Day Forecast State (Micro Task 3)
  forecastData: null,
  selectedForecastRegion: '北部地區',
  selectedForecastDate: '',
  forecastSourceMode: '',
};
if (typeof window !== 'undefined') {
  window.state = state;
}

// MapTiler basemaps. The browser key is restricted by Allowed HTTP Origins in MapTiler Cloud.
const MAPTILER_API_KEY = 'B9f2YXJnmuw4iY68TmG7';
const BASEMAPS = {
  dark: {
    url: `https://api.maptiler.com/maps/streets-v4-dark/256/{z}/{x}/{y}.png?key=${MAPTILER_API_KEY}`,
    attribution: '&copy; <a href="https://www.maptiler.com/copyright/">MapTiler</a> &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors ｜ 資料：中央氣象署',
  },
  light: {
    url: `https://api.maptiler.com/maps/streets-v4/256/{z}/{x}/{y}.png?key=${MAPTILER_API_KEY}`,
    attribution: '&copy; <a href="https://www.maptiler.com/copyright/">MapTiler</a> &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors ｜ 資料：中央氣象署',
  },
};

// DOM Elements
const elements = {
  map: document.getElementById('map'),
  sidebar: document.getElementById('sidebar'),
  btnToggleSidebar: document.getElementById('btn-toggle-sidebar'),
  btnCloseSidebar: document.getElementById('btn-close-sidebar'),
  btnRefresh: document.getElementById('btn-refresh'),
  syncStatus: document.getElementById('sync-status'),
  searchInput: document.getElementById('search-input'),
  searchResults: document.getElementById('search-results'),
  btnClearSearch: document.getElementById('btn-clear-search'),
  filterCounty: document.getElementById('filter-county'),
  filterTempCategory: document.getElementById('filter-temp-category'),
  toggleTempLabels: document.getElementById('toggle-temp-labels'),
  toggleDenseMode: document.getElementById('toggle-dense-mode'),
  toggleOffline: document.getElementById('toggle-offline'),
  toggleAutoRefresh: document.getElementById('toggle-auto-refresh'),
  btnBasemapDark: document.getElementById('btn-basemap-dark'),
  btnBasemapLight: document.getElementById('btn-basemap-light'),
  btnResetView: document.getElementById('btn-reset-view'),
  btnLocateMe: document.getElementById('btn-locate-me'),
  autoRefreshTimer: document.getElementById('auto-refresh-timer'),
  // 7-Day Forecast Elements (Micro Task 3)
  btnToggleForecast: document.getElementById('btn-toggle-forecast'),
  forecastPanel: document.getElementById('forecast-panel'),
  btnCloseForecast: document.getElementById('btn-close-forecast'),
  forecastModeBadge: document.getElementById('forecast-mode-badge'),
  forecastRegionSelect: document.getElementById('forecast-region-select'),
  forecastDateSelect: document.getElementById('forecast-date-select'),
  summaryRegionLabel: document.getElementById('summary-region-label'),
  summaryDateLabel: document.getElementById('summary-date-label'),
  summaryMintVal: document.getElementById('summary-mint-val'),
  summaryMaxtVal: document.getElementById('summary-maxt-val'),
  forecastChart: document.getElementById('forecast-chart'),
  forecastTableBody: document.getElementById('forecast-table-body'),
  forecastMetaSource: document.getElementById('forecast-meta-source'),
  forecastMetaMode: document.getElementById('forecast-meta-mode'),
  // Metrics
  metricTotalStations: document.getElementById('metric-total-stations'),
  metricMaxTemp: document.getElementById('metric-max-temp'),
  metricMaxTempSt: document.getElementById('metric-max-temp-st'),
  metricMinTemp: document.getElementById('metric-min-temp'),
  metricMinTempSt: document.getElementById('metric-min-temp-st'),
  metricAvgTemp: document.getElementById('metric-avg-temp'),
  metricMaxWind: document.getElementById('metric-max-wind'),
  // Sidebar Meta
  metaObsTime: document.getElementById('meta-obs-time'),
  metaGenTime: document.getElementById('meta-gen-time'),
  metaBuildMode: document.getElementById('meta-build-mode'),
  // Detail Panel
  detailPanel: document.getElementById('station-detail-panel'),
  btnCloseDetail: document.getElementById('btn-close-detail'),
  detailCounty: document.getElementById('detail-county'),
  detailName: document.getElementById('detail-name'),
  detailId: document.getElementById('detail-id'),
  detailTempBadge: document.getElementById('detail-temp-badge'),
  detailTemp: document.getElementById('detail-temp'),
  detailCategory: document.getElementById('detail-category'),
  detailWeather: document.getElementById('detail-weather'),
  detailHumidity: document.getElementById('detail-humidity'),
  detailWind: document.getElementById('detail-wind'),
  detailWindDir: document.getElementById('detail-wind-dir'),
  detailPrecipitation: document.getElementById('detail-precipitation'),
  detailPressure: document.getElementById('detail-pressure'),
  detailAltitude: document.getElementById('detail-altitude'),
  detailObsTime: document.getElementById('detail-obs-time'),
  btnFocusStation: document.getElementById('btn-focus-station'),
  toast: document.getElementById('toast'),
};

/**
 * Initialize Leaflet Map
 */
function initMap() {
  // Center of Taiwan: lat 23.75, lon 120.95
  state.map = L.map('map', {
    center: [23.75, 120.95],
    zoom: 8,
    minZoom: 6,
    maxZoom: 17,
    zoomControl: false,
  });

  // Custom Zoom Control top-right
  L.control.zoom({ position: 'bottomright' }).addTo(state.map);

  // Default to MapTiler dark basemap.
  setBasemap('dark');

  // Layer group for station markers
  state.markerLayer = L.layerGroup().addTo(state.map);

  // Map click deselects station
  state.map.on('click', (e) => {
    // If not clicked on a marker
    if (!e.originalEvent._markerClicked) {
      closeDetailPanel();
    }
  });

  // Zoom end re-evaluates density
  state.map.on('zoomend', () => {
    renderMarkers();
  });
}

/**
 * Switch MapTiler basemap.
 */
function setBasemap(theme) {
  const config = BASEMAPS[theme] || BASEMAPS.dark;

  if (state.currentTileLayer) {
    state.map.removeLayer(state.currentTileLayer);
  }

  state.currentTileLayer = L.tileLayer(config.url, {
    minZoom: 1,
    maxZoom: 19,
    tileSize: 256,
    crossOrigin: true,
    attribution: config.attribution,
  }).addTo(state.map);

  state.isDarkTheme = theme === 'dark';
  elements.btnBasemapDark?.classList.toggle('active', state.isDarkTheme);
  elements.btnBasemapLight?.classList.toggle('active', !state.isDarkTheme);
}

/**
 * Fetch Station Data from JSON endpoint
 */
async function loadData(showToastMsg = true) {
  elements.syncStatus.textContent = '更新中...';
  elements.btnRefresh.classList.add('loading');

  const stamp = Date.now();
  let payload = null;

  try {
    // Gate 3 primary path on Vercel: Flask reads the latest observations from SQLite.
    const apiRes = await fetch(`/api/weather?t=${stamp}`, { cache: 'no-store' });
    if (!apiRes.ok) throw new Error(`HTTP ${apiRes.status}`);
    payload = await apiRes.json();
  } catch (apiErr) {
    console.warn('[WARN] SQLite API unavailable; trying static stations.json:', apiErr);
    try {
      // GitHub Pages/static fallback: generated from the same normalized CWA snapshot.
      const jsonRes = await fetch(`./data/stations.json?t=${stamp}`, { cache: 'no-store' });
      if (!jsonRes.ok) throw new Error(`HTTP ${jsonRes.status}`);
      payload = await jsonRes.json();
    } catch (jsonErr) {
      console.warn('[WARN] stations.json unavailable; trying bundled fixture:', jsonErr);
      try {
        const fixRes = await fetch('./data/stations_fixture.json', { cache: 'no-store' });
        if (fixRes.ok) {
          payload = await fixRes.json();
          if (payload.features && !payload.stations) {
            payload = convertGeoJsonToSchema(payload);
          }
        }
      } catch (fixErr) {
        console.error('[ERROR] SQLite API, stations.json, and fixture all failed:', fixErr);
      }
    }
  }

  elements.btnRefresh.classList.remove('loading');

  if (!payload || !payload.stations) {
    elements.syncStatus.textContent = '載入失敗';
    showToast('無法讀取測站資料，請確認網路連線');
    return;
  }

  state.data = payload;
  state.stations = payload.stations || [];

  elements.syncStatus.textContent = '已同步';
  if (showToastMsg) {
    showToast(`成功載入 ${state.stations.length} 個全台氣象測站`);
  }

  updateMetrics();
  populateCountiesDropdown();
  applyFilters();
  resetCountdown();
}

/**
 * Helper to convert GeoJSON fixture if loaded directly
 */
function convertGeoJsonToSchema(geojson) {
  const stations = [];
  const features = geojson.features || [];
  for (const f of features) {
    const p = f.properties || {};
    const coords = f.geometry?.coordinates || [null, null];
    const temp = p.temperature !== undefined && p.temperature !== null ? Number(p.temperature) : null;
    stations.push({
      station_id: p.stationId || '',
      station_name: p.stationName || '未命名',
      county: p.county || '其他',
      town: p.town || '',
      lat: coords[1],
      lon: coords[0],
      obs_time: p.observedAt || '',
      weather: p.weather || '晴',
      temperature: temp,
      humidity: p.humidity,
      pressure: p.pressure,
      wind_speed: p.windSpeed,
      wind_direction: p.windDirection,
      gust_speed: p.gustSpeed,
      precipitation: p.precipitation,
      color: getTempColor(temp),
      category: getTempCategory(temp),
      has_temp: temp !== null,
    });
  }
  return {
    metadata: {
      source: 'CWA O-A0003-001 (Fixture)',
      generated_at: new Date().toISOString(),
      observation_time: stations[0]?.obs_time || new Date().toISOString(),
      total_stations: stations.length,
      valid_temp_stations: stations.filter(s => s.has_temp).length,
      build_mode: 'client_fallback',
      stats: {
        max_temperature: { value: 30.7, station_name: '安溪寮', county: '嘉義縣' },
        min_temperature: { value: 7.2, station_name: '玉山', county: '南投縣' },
        avg_temperature: 26.8,
        max_wind_speed: { value: 10.0, station_name: '西濱S023K' },
      },
      counties: Array.from(new Set(stations.map(s => s.county))).sort(),
    },
    stations,
  };
}

function getTempColor(t) {
  if (t === null || t === undefined) return '#94A3B8';
  if (t < 10) return '#2563EB';
  if (t < 15) return '#06B6D4';
  if (t < 20) return '#10B981';
  if (t < 25) return '#EAB308';
  if (t < 30) return '#F97316';
  if (t < 35) return '#EF4444';
  return '#991B1B';
}

function getTempCategory(t) {
  if (t === null || t === undefined) return '無資料';
  if (t < 10) return '嚴寒 (<10°C)';
  if (t < 15) return '寒冷 (10-15°C)';
  if (t < 20) return '涼爽 (15-20°C)';
  if (t < 25) return '舒適 (20-25°C)';
  if (t < 30) return '溫暖 (25-30°C)';
  if (t < 35) return '炎熱 (30-35°C)';
  return '酷熱 (>35°C)';
}

/**
 * Update Top Metric Banners and Metadata
 */
function updateMetrics() {
  const meta = state.data?.metadata || {};
  const stats = meta.stats || {};

  elements.metricTotalStations.textContent = `${meta.total_stations || state.stations.length} 站`;

  // Max Temp
  if (stats.max_temperature && stats.max_temperature.value !== null) {
    elements.metricMaxTemp.textContent = `${stats.max_temperature.value}°C`;
    elements.metricMaxTempSt.textContent = `${stats.max_temperature.station_name} (${stats.max_temperature.county || ''})`;
  } else {
    elements.metricMaxTemp.textContent = '--';
    elements.metricMaxTempSt.textContent = '';
  }

  // Min Temp
  if (stats.min_temperature && stats.min_temperature.value !== null) {
    elements.metricMinTemp.textContent = `${stats.min_temperature.value}°C`;
    elements.metricMinTempSt.textContent = `${stats.min_temperature.station_name} (${stats.min_temperature.county || ''})`;
  } else {
    elements.metricMinTemp.textContent = '--';
    elements.metricMinTempSt.textContent = '';
  }

  // Avg Temp
  elements.metricAvgTemp.textContent = stats.avg_temperature ? `${stats.avg_temperature}°C` : '--';

  // Max Wind
  if (stats.max_wind_speed && stats.max_wind_speed.value !== null) {
    elements.metricMaxWind.textContent = `${stats.max_wind_speed.value} m/s (${stats.max_wind_speed.station_name})`;
  } else {
    elements.metricMaxWind.textContent = '--';
  }

  // Metadata timestamps
  elements.metaObsTime.textContent = formatDateTime(meta.observation_time);
  elements.metaGenTime.textContent = formatDateTime(meta.generated_at);
  elements.metaBuildMode.textContent = meta.build_mode || '即時連線';
}

/**
 * Populate County Dropdown
 */
function populateCountiesDropdown() {
  const counties = state.data?.metadata?.counties || [];
  const currentVal = elements.filterCounty.value;

  elements.filterCounty.innerHTML = '<option value="ALL">全部縣市 (全台檢視)</option>';
  for (const c of counties) {
    const opt = document.createElement('option');
    opt.value = c;
    opt.textContent = c;
    elements.filterCounty.appendChild(opt);
  }

  if (counties.includes(currentVal)) {
    elements.filterCounty.value = currentVal;
  }
}

/**
 * Apply Filters (County, Temp Category, Offline)
 */
function applyFilters() {
  const selectedCounty = elements.filterCounty.value;
  const selectedCategory = elements.filterTempCategory.value;
  const includeOffline = elements.toggleOffline.checked;

  state.filteredStations = state.stations.filter((st) => {
    // 1. County Filter
    if (selectedCounty !== 'ALL' && st.county !== selectedCounty) {
      return false;
    }

    // 2. Offline / No Temp Filter
    if (!includeOffline && !st.has_temp) {
      return false;
    }

    // 3. Temperature Category Filter
    if (selectedCategory !== 'ALL') {
      const t = st.temperature;
      if (t === null) return false;
      if (selectedCategory === 'cold' && t >= 10) return false;
      if (selectedCategory === 'cool' && (t < 10 || t >= 20)) return false;
      if (selectedCategory === 'comfort' && (t < 20 || t >= 25)) return false;
      if (selectedCategory === 'warm' && (t < 25 || t >= 30)) return false;
      if (selectedCategory === 'hot' && t < 30) return false;
    }

    return true;
  });

  renderMarkers();
}

/**
 * Render Station Markers onto Map
 */
function renderMarkers() {
  state.markerLayer.clearLayers();
  state.markersMap.clear();

  const showLabels = elements.toggleTempLabels.checked;
  const denseMode = elements.toggleDenseMode.checked;
  const currentZoom = state.map.getZoom();

  // If zoomed far out (<= 8) and dense mode is on, use compact dot markers
  const useCompactDots = denseMode && currentZoom <= 7;

  for (const st of state.filteredStations) {
    if (st.lat === null || st.lon === null) continue;

    const color = st.color || '#94A3B8';
    const tempText = st.temperature !== null ? `${Math.round(st.temperature)}°` : '-';

    let iconHtml = '';
    let iconClass = 'cwa-marker-badge';
    let iconSize = [36, 22];

    if (useCompactDots) {
      iconClass += ' dense-dot';
      iconSize = [14, 14];
      iconHtml = '';
    } else if (showLabels) {
      iconClass += ' labeled';
      iconHtml = `<span>${tempText}</span>`;
      iconSize = [tempText.length > 2 ? 40 : 34, 22];
    } else {
      iconClass += ' dense-dot';
      iconSize = [16, 16];
      iconHtml = '';
    }

    const icon = L.divIcon({
      className: '',
      html: `<div class="${iconClass}" style="background-color: ${color};">${iconHtml}</div>`,
      iconSize: iconSize,
      iconAnchor: [iconSize[0] / 2, iconSize[1] / 2],
    });

    const marker = L.marker([st.lat, st.lon], {
      icon: icon,
      title: `${st.station_name} (${st.county}${st.town})：${st.temperature !== null ? st.temperature + '°C' : '無溫度'}`,
      riseOnHover: true,
    });

    // Marker click event
    marker.on('click', (e) => {
      e.originalEvent._markerClicked = true;
      selectStation(st, marker);
    });

    marker.addTo(state.markerLayer);
    state.markersMap.set(st.station_id, marker);
  }
}

/**
 * Select Station and Show Detail Panel
 */
function selectStation(st, marker = null) {
  state.selectedStation = st;

  // Highlight marker
  document.querySelectorAll('.cwa-marker-badge.selected').forEach((el) => el.classList.remove('selected'));
  if (marker && marker.getElement()) {
    const badge = marker.getElement().querySelector('.cwa-marker-badge');
    if (badge) badge.classList.add('selected');
  }

  // Populate Details
  elements.detailCounty.textContent = `${st.county} · ${st.town || ''}`;
  elements.detailName.textContent = st.station_name;
  elements.detailId.textContent = `ID: ${st.station_id}`;

  if (st.temperature !== null) {
    elements.detailTemp.textContent = st.temperature.toFixed(1);
    elements.detailTempBadge.style.backgroundColor = st.color;
    // Dark font for yellowish background
    if (st.temperature >= 20 && st.temperature < 25) {
      elements.detailTempBadge.style.color = '#0f172a';
    } else {
      elements.detailTempBadge.style.color = '#ffffff';
    }
  } else {
    elements.detailTemp.textContent = '--';
    elements.detailTempBadge.style.backgroundColor = '#94A3B8';
    elements.detailTempBadge.style.color = '#ffffff';
  }

  elements.detailCategory.textContent = st.category || '一般';
  elements.detailCategory.style.backgroundColor = st.color;
  elements.detailWeather.textContent = `天氣現象：${st.weather || '晴'}`;

  elements.detailHumidity.textContent = st.humidity !== null ? `${st.humidity} %` : '無資料';
  elements.detailWind.textContent = st.wind_speed !== null ? `${st.wind_speed} m/s` : '無資料';

  const dirText = st.wind_direction !== null ? `${st.wind_direction}°` : '靜風';
  const gustText = st.gust_speed !== null ? `${st.gust_speed} m/s` : '--';
  elements.detailWindDir.textContent = `${dirText} / ${gustText}`;

  elements.detailPrecipitation.textContent = st.precipitation !== null ? `${st.precipitation} mm` : '0.0 mm';
  elements.detailPressure.textContent = st.pressure !== null ? `${st.pressure} hPa` : '無資料';
  elements.detailAltitude.textContent = (st.altitude !== null && st.altitude !== undefined) ? `${st.altitude} m` : '平地站 / 未提供';
  elements.detailObsTime.textContent = formatDateTime(st.obs_time);

  // Show panel
  elements.detailPanel.style.display = 'flex';
}

function closeDetailPanel() {
  state.selectedStation = null;
  elements.detailPanel.style.display = 'none';
  document.querySelectorAll('.cwa-marker-badge.selected').forEach((el) => el.classList.remove('selected'));
}

/**
 * Search Autocomplete and Handler
 */
function setupSearch() {
  elements.searchInput.addEventListener('input', (e) => {
    const query = e.target.value.trim().toLowerCase();
    if (!query) {
      elements.searchResults.style.display = 'none';
      elements.btnClearSearch.style.display = 'none';
      return;
    }

    elements.btnClearSearch.style.display = 'block';

    const matches = state.stations
      .filter((s) => {
        return (
          s.station_name.toLowerCase().includes(query) ||
          s.county.toLowerCase().includes(query) ||
          (s.town && s.town.toLowerCase().includes(query)) ||
          s.station_id.toLowerCase().includes(query)
        );
      })
      .slice(0, 8);

    if (matches.length === 0) {
      elements.searchResults.innerHTML = '<div class="search-item" style="color: #94a3b8;">查無相符測站</div>';
      elements.searchResults.style.display = 'block';
      return;
    }

    elements.searchResults.innerHTML = matches
      .map((s) => {
        const tempText = s.temperature !== null ? `${s.temperature}°C` : '--';
        return `
        <div class="search-item" data-id="${s.station_id}">
          <div>
            <strong>${s.station_name}</strong>
            <span class="st-meta">${s.county} ${s.town || ''}</span>
          </div>
          <span class="st-temp" style="background-color: ${s.color}; color: #fff;">${tempText}</span>
        </div>
      `;
      })
      .join('');

    elements.searchResults.style.display = 'block';
  });

  elements.searchResults.addEventListener('click', (e) => {
    const item = e.target.closest('.search-item');
    if (!item) return;

    const stationId = item.dataset.id;
    const station = state.stations.find((s) => s.station_id === stationId);
    if (station) {
      elements.searchResults.style.display = 'none';
      elements.searchInput.value = station.station_name;

      // Pan & Zoom to Station
      state.map.flyTo([station.lat, station.lon], 13, { duration: 1.2 });

      setTimeout(() => {
        const marker = state.markersMap.get(station.station_id);
        selectStation(station, marker);
      }, 600);
    }
  });

  elements.btnClearSearch.addEventListener('click', () => {
    elements.searchInput.value = '';
    elements.searchResults.style.display = 'none';
    elements.btnClearSearch.style.display = 'none';
  });
}

/**
 * Auto Refresh Timer & Countdown
 */
function resetCountdown() {
  state.countdownSeconds = 300; // 5 minutes
  updateCountdownDisplay();

  if (state.countdownInterval) clearInterval(state.countdownInterval);

  state.countdownInterval = setInterval(() => {
    if (!elements.toggleAutoRefresh.checked) return;

    state.countdownSeconds -= 1;
    if (state.countdownSeconds <= 0) {
      state.countdownSeconds = 300;
      loadData(false);
    }
    updateCountdownDisplay();
  }, 1000);
}

function updateCountdownDisplay() {
  const mins = Math.floor(state.countdownSeconds / 60);
  const secs = state.countdownSeconds % 60;
  elements.autoRefreshTimer.textContent = `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
}

/**
 * Format ISO datetime string for human readability
 */
function formatDateTime(isoString) {
  if (!isoString) return '--';
  try {
    const d = new Date(isoString);
    if (isNaN(d.getTime())) return isoString;
    const month = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    const hours = String(d.getHours()).padStart(2, '0');
    const minutes = String(d.getMinutes()).padStart(2, '0');
    return `${month}/${day} ${hours}:${minutes}`;
  } catch {
    return isoString;
  }
}

/**
 * Toast Notification Helper
 */
function showToast(msg, duration = 3000) {
  elements.toast.textContent = msg;
  elements.toast.style.display = 'block';
  setTimeout(() => {
    elements.toast.style.display = 'none';
  }, duration);
}

/* ==========================================================================
   7-Day Regional Temperature Forecast Implementation (Micro Task 3)
   ========================================================================== */

/**
 * Normalizes raw F-A0010-001 fixture if loaded directly
 */
function normalizeRawForecastFixture(raw) {
  try {
    if (!raw) return null;
    if (raw.forecasts || raw.rows) return raw;
    const locations =
      raw?.cwaopendata?.resources?.resource?.data?.agrWeatherForecasts?.weatherForecasts?.location || [];
    const rows = [];
    const regions = [];
    for (const loc of locations) {
      const regionName = loc.locationName;
      if (regionName && !regions.includes(regionName)) {
        regions.push(regionName);
      }
      const maxList = loc.weatherElements?.MaxT?.daily || [];
      const minList = loc.weatherElements?.MinT?.daily || [];
      const minMap = {};
      for (const m of minList) {
        if (m.dataDate) minMap[m.dataDate] = parseFloat(m.temperature);
      }
      for (const m of maxList) {
        const d = m.dataDate;
        rows.push({
          regionName,
          dataDate: d,
          mint: minMap[d] !== undefined ? minMap[d] : null,
          maxt: parseFloat(m.temperature),
        });
      }
    }
    return {
      metadata: {
        source: 'CWA F-A0010-001 (Fixture)',
        source_dataset: 'F-A0010-001',
        build_mode: 'fallback_fixture',
        total_regions: regions.length,
        total_records: rows.length,
        regions: regions,
      },
      regions: regions,
      rows: rows,
      forecasts: rows,
    };
  } catch (err) {
    console.error('Error normalizing raw forecast fixture:', err);
    return null;
  }
}

/**
 * Format date string with weekday in Traditional Chinese: "YYYY-MM-DD (週X)"
 */
function formatForecastDate(dateStr) {
  if (!dateStr) return '--';
  try {
    const parts = dateStr.split('-');
    if (parts.length === 3) {
      const d = new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
      const days = ['週日', '週一', '週二', '週三', '週四', '週五', '週六'];
      const dayName = days[d.getDay()];
      return `${dateStr} (${dayName})`;
    }
    return dateStr;
  } catch {
    return dateStr;
  }
}

/**
 * Fetch 7-Day forecast data with 3-tier cascade:
 * 1. /api/forecast (SQLite-backed)
 * 2. ./data/forecast.json (static fallback for GitHub Pages)
 * 3. ./data/forecast_fixture.json (offline fallback fixture)
 */
async function loadForecastData() {
  if (elements.forecastModeBadge) {
    elements.forecastModeBadge.textContent = '載入中...';
    elements.forecastModeBadge.style.background = 'rgba(148, 163, 184, 0.2)';
    elements.forecastModeBadge.style.color = '#94a3b8';
  }

  const stamp = Date.now();
  let payload = null;
  let sourceMode = 'unknown';

  try {
    const apiRes = await fetch(`/api/forecast?t=${stamp}`, { cache: 'no-store' });
    if (!apiRes.ok) throw new Error(`HTTP ${apiRes.status}`);
    payload = await apiRes.json();
    sourceMode = 'live_api';
  } catch (apiErr) {
    console.warn('[WARN] Forecast API unavailable; trying static forecast.json:', apiErr);
    try {
      const jsonRes = await fetch(`./data/forecast.json?t=${stamp}`, { cache: 'no-store' });
      if (!jsonRes.ok) throw new Error(`HTTP ${jsonRes.status}`);
      payload = await jsonRes.json();
      sourceMode = 'static_json';
    } catch (jsonErr) {
      console.warn('[WARN] forecast.json unavailable; trying bundled forecast_fixture.json:', jsonErr);
      try {
        const fixRes = await fetch('./data/forecast_fixture.json', { cache: 'no-store' });
        if (fixRes.ok) {
          const raw = await fixRes.json();
          payload = normalizeRawForecastFixture(raw);
          sourceMode = 'fixture';
        }
      } catch (fixErr) {
        console.error('[ERROR] All forecast sources failed:', fixErr);
      }
    }
  }

  if (!payload || (!payload.forecasts && !payload.rows)) {
    if (elements.forecastModeBadge) {
      elements.forecastModeBadge.textContent = '載入失敗';
      elements.forecastModeBadge.style.background = 'rgba(239, 68, 68, 0.2)';
      elements.forecastModeBadge.style.color = '#f87171';
    }
    if (elements.forecastTableBody) {
      elements.forecastTableBody.innerHTML =
        '<tr><td colspan="3" style="text-align: center; color: #f87171;">無法讀取預報資料</td></tr>';
    }
    return;
  }

  state.forecastData = payload;
  state.forecastSourceMode = sourceMode;

  updateForecastMetadata();
  populateForecastRegionsDropdown();
  updateForecastUI();
}

/**
 * Display source dataset and operation mode
 */
function updateForecastMetadata() {
  const meta = state.forecastData?.metadata || {};
  const mode = state.forecastSourceMode;

  if (elements.forecastModeBadge) {
    if (mode === 'live_api') {
      elements.forecastModeBadge.textContent = '即時連線 (Live API)';
      elements.forecastModeBadge.style.background = 'rgba(16, 185, 129, 0.2)';
      elements.forecastModeBadge.style.color = '#34d399';
    } else if (mode === 'static_json') {
      const isLive = meta.build_mode === 'live_cwa_api';
      elements.forecastModeBadge.textContent = isLive ? '靜態同步 (Live Snapshot)' : '靜態備援';
      elements.forecastModeBadge.style.background = 'rgba(6, 182, 212, 0.2)';
      elements.forecastModeBadge.style.color = '#22d3ee';
    } else {
      elements.forecastModeBadge.textContent = '備援資料 (Fixture)';
      elements.forecastModeBadge.style.background = 'rgba(245, 158, 11, 0.2)';
      elements.forecastModeBadge.style.color = '#fbbf24';
    }
  }

  if (elements.forecastMetaSource) {
    elements.forecastMetaSource.textContent = meta.source || meta.source_dataset || '中央氣象署 F-C0032-003';
  }

  if (elements.forecastMetaMode) {
    const rawMode = meta.build_mode || mode;
    elements.forecastMetaMode.textContent = rawMode;
  }
}

/**
 * Populate forecast regions selector
 */
function populateForecastRegionsDropdown() {
  const defaultRegions = ['北部地區', '中部地區', '南部地區', '東北部地區', '東部地區', '東南部地區'];
  const regions = state.forecastData?.regions || defaultRegions;

  if (!elements.forecastRegionSelect) return;

  const currentVal = elements.forecastRegionSelect.value || state.selectedForecastRegion;
  elements.forecastRegionSelect.innerHTML = '';
  for (const r of regions) {
    const opt = document.createElement('option');
    opt.value = r;
    opt.textContent = r;
    elements.forecastRegionSelect.appendChild(opt);
  }

  if (regions.includes(currentVal)) {
    elements.forecastRegionSelect.value = currentVal;
    state.selectedForecastRegion = currentVal;
  } else if (regions.length > 0) {
    elements.forecastRegionSelect.value = regions[0];
    state.selectedForecastRegion = regions[0];
  }
}

/**
 * Filter 7-day rows for current region
 */
function getForecastRowsForRegion(regionName) {
  const allRows = state.forecastData?.rows || state.forecastData?.forecasts || [];
  return allRows
    .filter((r) => r.regionName === regionName)
    .sort((a, b) => a.dataDate.localeCompare(b.dataDate));
}

/**
 * Update UI for forecast: date selector, summary card, chart, and table
 */
function updateForecastUI() {
  const rows = getForecastRowsForRegion(state.selectedForecastRegion);
  if (!rows || rows.length === 0) {
    if (elements.forecastTableBody) {
      elements.forecastTableBody.innerHTML =
        '<tr><td colspan="3" style="text-align: center; color: var(--text-dim);">此地區無預報資料</td></tr>';
    }
    return;
  }

  // Ensure selected date exists in rows
  const availableDates = rows.map((r) => r.dataDate);
  if (!state.selectedForecastDate || !availableDates.includes(state.selectedForecastDate)) {
    state.selectedForecastDate = availableDates[0];
  }

  // Update date selector
  if (elements.forecastDateSelect) {
    elements.forecastDateSelect.innerHTML = '';
    for (const r of rows) {
      const opt = document.createElement('option');
      opt.value = r.dataDate;
      opt.textContent = formatForecastDate(r.dataDate);
      elements.forecastDateSelect.appendChild(opt);
    }
    elements.forecastDateSelect.value = state.selectedForecastDate;
  }

  // Update Summary Card
  const selectedRow = rows.find((r) => r.dataDate === state.selectedForecastDate) || rows[0];
  if (selectedRow) {
    if (elements.summaryRegionLabel) elements.summaryRegionLabel.textContent = selectedRow.regionName;
    if (elements.summaryDateLabel) elements.summaryDateLabel.textContent = formatForecastDate(selectedRow.dataDate);
    if (elements.summaryMintVal) {
      elements.summaryMintVal.textContent = selectedRow.mint !== null ? Math.round(selectedRow.mint) : '--';
    }
    if (elements.summaryMaxtVal) {
      elements.summaryMaxtVal.textContent = selectedRow.maxt !== null ? Math.round(selectedRow.maxt) : '--';
    }
  }

  // Render Table & Chart
  renderForecastTable(rows, state.selectedForecastDate);
  renderForecastChart(rows, state.selectedForecastDate);
}

/**
 * Select a forecast date and refresh views
 */
function selectForecastDate(dateStr) {
  state.selectedForecastDate = dateStr;
  if (elements.forecastDateSelect) {
    elements.forecastDateSelect.value = dateStr;
  }
  updateForecastUI();
}

/**
 * Render 7-Day Forecast Table
 */
function renderForecastTable(rows, selectedDate) {
  if (!elements.forecastTableBody) return;

  elements.forecastTableBody.innerHTML = '';
  for (const r of rows) {
    const tr = document.createElement('tr');
    const isSelected = r.dataDate === selectedDate;
    if (isSelected) tr.classList.add('selected');

    const mintDisplay = r.mint !== null ? `<span style="color: #60a5fa; font-weight: 700;">${Math.round(r.mint)}°C</span>` : '--';
    const maxtDisplay = r.maxt !== null ? `<span style="color: #f87171; font-weight: 700;">${Math.round(r.maxt)}°C</span>` : '--';

    tr.innerHTML = `
      <td>${formatForecastDate(r.dataDate)}</td>
      <td>${mintDisplay}</td>
      <td>${maxtDisplay}</td>
    `;

    tr.addEventListener('click', () => {
      selectForecastDate(r.dataDate);
    });

    elements.forecastTableBody.appendChild(tr);
  }
}

/**
 * Render Native SVG 7-Day Temperature Line Chart
 */
function renderForecastChart(rows, selectedDate) {
  const svg = elements.forecastChart;
  if (!svg || rows.length === 0) return;

  const width = 320;
  const height = 150;
  const padLeft = 32;
  const padRight = 20;
  const padTop = 22;
  const padBottom = 26;
  const chartW = width - padLeft - padRight;
  const chartH = height - padTop - padBottom;

  const allTemps = [];
  rows.forEach((r) => {
    if (r.mint !== null && !isNaN(r.mint)) allTemps.push(r.mint);
    if (r.maxt !== null && !isNaN(r.maxt)) allTemps.push(r.maxt);
  });

  let minT = allTemps.length > 0 ? Math.min(...allTemps) : 15;
  let maxT = allTemps.length > 0 ? Math.max(...allTemps) : 35;
  minT = Math.floor(minT - 2);
  maxT = Math.ceil(maxT + 2);
  if (maxT <= minT) maxT = minT + 8;

  function getX(index) {
    if (rows.length <= 1) return padLeft + chartW / 2;
    return padLeft + (index / (rows.length - 1)) * chartW;
  }

  function getY(temp) {
    if (temp === null || isNaN(temp)) return padTop + chartH;
    return padTop + (1 - (temp - minT) / (maxT - minT)) * chartH;
  }

  let svgContent = '';

  // 1. Subtle horizontal grid lines & temp labels
  const gridSteps = [minT + 2, Math.round((minT + maxT) / 2), maxT - 2];
  gridSteps.forEach((stepT) => {
    const y = getY(stepT);
    svgContent += `
      <line x1="${padLeft}" y1="${y}" x2="${width - padRight}" y2="${y}" stroke="rgba(255, 255, 255, 0.08)" stroke-width="1" />
      <text x="${padLeft - 4}" y="${y + 3}" text-anchor="end" fill="#64748b" font-size="9" font-family="JetBrains Mono, monospace">${stepT}°</text>
    `;
  });

  // 2. Selected date highlight column
  rows.forEach((r, i) => {
    if (r.dataDate === selectedDate) {
      const cx = getX(i);
      svgContent += `
        <line x1="${cx}" y1="${padTop - 8}" x2="${cx}" y2="${height - padBottom + 2}" stroke="rgba(255, 255, 255, 0.35)" stroke-width="1.5" stroke-dasharray="3 3" />
      `;
    }
  });

  // 3. MaxT and MinT Polylines
  const maxPoints = rows.map((r, i) => `${getX(i).toFixed(1)},${getY(r.maxt).toFixed(1)}`).join(' ');
  const minPoints = rows.map((r, i) => `${getX(i).toFixed(1)},${getY(r.mint).toFixed(1)}`).join(' ');

  svgContent += `
    <polyline fill="none" stroke="#f87171" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" points="${maxPoints}" />
    <polyline fill="none" stroke="#60a5fa" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" points="${minPoints}" />
  `;

  // 4. Data points, value badges, and X-axis labels
  rows.forEach((r, i) => {
    const cx = getX(i);
    const yMax = getY(r.maxt);
    const yMin = getY(r.mint);
    const isSelected = r.dataDate === selectedDate;

    // Max circle
    const rMaxRadius = isSelected ? 5.5 : 3.5;
    const rMaxStroke = isSelected ? '#ffffff' : '#0f172a';
    const rMaxStrokeW = isSelected ? 2 : 1.5;
    svgContent += `
      <circle cx="${cx.toFixed(1)}" cy="${yMax.toFixed(1)}" r="${rMaxRadius}" fill="#f87171" stroke="${rMaxStroke}" stroke-width="${rMaxStrokeW}" />
    `;

    // Min circle
    const rMinRadius = isSelected ? 5.5 : 3.5;
    const rMinStroke = isSelected ? '#ffffff' : '#0f172a';
    const rMinStrokeW = isSelected ? 2 : 1.5;
    svgContent += `
      <circle cx="${cx.toFixed(1)}" cy="${yMin.toFixed(1)}" r="${rMinRadius}" fill="#60a5fa" stroke="${rMinStroke}" stroke-width="${rMinStrokeW}" />
    `;

    // Text labels for selected point
    if (isSelected) {
      if (r.maxt !== null) {
        svgContent += `
          <text x="${cx.toFixed(1)}" y="${(yMax - 9).toFixed(1)}" text-anchor="middle" fill="#f87171" font-size="10" font-weight="700" font-family="JetBrains Mono, monospace">${Math.round(r.maxt)}°</text>
        `;
      }
      if (r.mint !== null) {
        svgContent += `
          <text x="${cx.toFixed(1)}" y="${(yMin + 16).toFixed(1)}" text-anchor="middle" fill="#60a5fa" font-size="10" font-weight="700" font-family="JetBrains Mono, monospace">${Math.round(r.mint)}°</text>
        `;
      }
    }

    // X-axis date label
    const shortDate = r.dataDate.slice(5).replace('-', '/');
    const labelColor = isSelected ? '#ffffff' : '#94a3b8';
    const labelWeight = isSelected ? '700' : '500';
    svgContent += `
      <text x="${cx.toFixed(1)}" y="${height - 8}" text-anchor="middle" fill="${labelColor}" font-weight="${labelWeight}" font-size="9" font-family="Inter, sans-serif">${shortDate}</text>
    `;

    // Interactive clickable hit area for column
    svgContent += `
      <rect x="${(cx - 18).toFixed(1)}" y="${padTop - 10}" width="36" height="${chartH + 30}" fill="transparent" style="cursor: pointer;" data-date="${r.dataDate}" />
    `;
  });

  svg.innerHTML = svgContent;

  // Add click handlers on interactive SVG elements
  svg.querySelectorAll('rect[data-date]').forEach((rect) => {
    rect.addEventListener('click', (e) => {
      const d = e.target.getAttribute('data-date');
      if (d) selectForecastDate(d);
    });
  });
}

/**
 * Bind User Event Listeners
 */
function bindEvents() {
  // Sidebar Toggles
  elements.btnToggleSidebar.addEventListener('click', () => {
    elements.sidebar.classList.toggle('closed');
  });
  elements.btnCloseSidebar.addEventListener('click', () => {
    elements.sidebar.classList.add('closed');
  });

  // 7-Day Forecast Panel Toggles
  if (elements.btnToggleForecast && elements.forecastPanel) {
    elements.btnToggleForecast.addEventListener('click', () => {
      elements.forecastPanel.classList.toggle('closed');
      const isOpen = !elements.forecastPanel.classList.contains('closed');
      elements.btnToggleForecast.classList.toggle('active', isOpen);
    });
  }
  if (elements.btnCloseForecast && elements.forecastPanel) {
    elements.btnCloseForecast.addEventListener('click', () => {
      elements.forecastPanel.classList.add('closed');
      elements.btnToggleForecast?.classList.remove('active');
    });
  }

  // 7-Day Forecast Controls
  if (elements.forecastRegionSelect) {
    elements.forecastRegionSelect.addEventListener('change', (e) => {
      state.selectedForecastRegion = e.target.value;
      updateForecastUI();
    });
  }
  if (elements.forecastDateSelect) {
    elements.forecastDateSelect.addEventListener('change', (e) => {
      state.selectedForecastDate = e.target.value;
      updateForecastUI();
    });
  }

  // Refresh
  elements.btnRefresh.addEventListener('click', () => {
    loadData(true);
    loadForecastData();
  });

  // Filter Changes
  elements.filterCounty.addEventListener('change', () => {
    applyFilters();
    // If county selected, fly to county bounds
    const county = elements.filterCounty.value;
    if (county !== 'ALL') {
      const countyStations = state.filteredStations.filter((s) => s.county === county);
      if (countyStations.length > 0) {
        const bounds = L.latLngBounds(countyStations.map((s) => [s.lat, s.lon]));
        state.map.fitBounds(bounds, { padding: [50, 50], maxZoom: 12 });
      }
    } else {
      state.map.flyTo([23.75, 120.95], 8);
    }
  });

  elements.filterTempCategory.addEventListener('change', applyFilters);
  elements.toggleTempLabels.addEventListener('change', renderMarkers);
  elements.toggleDenseMode.addEventListener('change', renderMarkers);
  elements.toggleOffline.addEventListener('change', applyFilters);

  // Basemap Toggles
  elements.btnBasemapDark.addEventListener('click', () => setBasemap('dark'));
  elements.btnBasemapLight.addEventListener('click', () => setBasemap('light'));

  // Quick View Preset Buttons
  elements.btnResetView.addEventListener('click', () => {
    elements.filterCounty.value = 'ALL';
    applyFilters();
    state.map.flyTo([23.75, 120.95], 8);
  });

  elements.btnLocateMe.addEventListener('click', () => {
    if (!navigator.geolocation) {
      showToast('瀏覽器不支援定位功能');
      return;
    }
    showToast('正在偵測您的位置...');
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const lat = pos.coords.latitude;
        const lon = pos.coords.longitude;
        state.map.flyTo([lat, lon], 12);
        L.circleMarker([lat, lon], {
          radius: 8,
          fillColor: '#38bdf8',
          color: '#ffffff',
          weight: 3,
          fillOpacity: 0.9,
        })
          .addTo(state.map)
          .bindPopup('您目前的位置')
          .openPopup();
      },
      () => {
        showToast('無法取得定位，請確認定位權限');
      }
    );
  });

  // Detail Panel Close & Focus
  elements.btnCloseDetail.addEventListener('click', closeDetailPanel);
  elements.btnFocusStation.addEventListener('click', () => {
    if (state.selectedStation) {
      state.map.flyTo([state.selectedStation.lat, state.selectedStation.lon], 14);
    }
  });
}

// App Entry Point
document.addEventListener('DOMContentLoaded', () => {
  initMap();
  setupSearch();
  bindEvents();
  loadData(false);
  loadForecastData();
  window.selectStation = selectStation;
  window.selectForecastDate = selectForecastDate;
});
