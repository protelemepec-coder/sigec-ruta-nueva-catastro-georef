// SIGEC - EPEC: Visor Geoespacial de Manzanas Catastrales por Rutas de Lectura
// Distrito 1 - Optimizado con Canvas Renderer para 18.721 Manzanas

document.addEventListener('DOMContentLoaded', () => {
  const loadingOverlay = document.getElementById('loadingOverlay');
  const loadingText = document.getElementById('loadingText');
  const searchInput = document.getElementById('searchInput');
  const cycleSelect = document.getElementById('cycleSelect');
  const colorModeSelect = document.getElementById('colorModeSelect');
  
  // Elementos de Inspección y Filtros
  const inspectorPanel = document.getElementById('inspectorPanel');
  const inspectorClose = document.getElementById('inspectorClose');
  const btnIsolateRoute = document.getElementById('btnIsolateRoute');
  const btnDeselectMza = document.getElementById('btnDeselectMza');
  const btnCleanFilter = document.getElementById('btnCleanFilter');
  const btnResetView = document.getElementById('btnResetView');
  const filterStatusBadge = document.getElementById('filterStatusBadge');
  const filterStatusText = document.getElementById('filterStatusText');
  const btnRemoveFilterBadge = document.getElementById('btnRemoveFilterBadge');
  
  // Botones de Navegación y Zoom
  const btnZoomIn = document.getElementById('btnZoomIn');
  const btnZoomOut = document.getElementById('btnZoomOut');
  const btnFitDistrict = document.getElementById('btnFitDistrict');
  const btnFloatClear = document.getElementById('btnFloatClear');
  
  // Ficha de Inspección
  const inspMza = document.getElementById('inspMza');
  const inspRutaBadge = document.getElementById('inspRutaBadge');
  const inspGrupo = document.getElementById('inspGrupo');
  const inspSumis = document.getElementById('inspSumis');
  const inspCalles = document.getElementById('inspCalles');
  const inspAlturas = document.getElementById('inspAlturas');
  const inspFuente = document.getElementById('inspFuente');
  
  // Contadores KPI
  const kpiMzas = document.getElementById('kpiMzas');
  const kpiRutas = document.getElementById('kpiRutas');
  const kpiSumis = document.getElementById('kpiSumis');
  
  let currentSelectedFeature = null;
  let activeIsolatedRoute = null;
  let activeCycleFilter = 'all';
  let currentColorMode = 'route'; // 'route', 'cycle', 'density'
  
  // 1. Inicializar Mapa Leaflet con soporte de zoom
  const map = L.map('map', {
    center: [-31.4201, -64.1888], // Córdoba Capital Centro
    zoom: 13,
    minZoom: 10,
    maxZoom: 19,
    preferCanvas: true,
    scrollWheelZoom: true,
    zoomControl: false // Usamos nuestra barra personalizada integrada
  });
  
  // Renderer Canvas ultra-rápido para 18.721 polígonos a 60 FPS
  const canvasRenderer = L.canvas({ padding: 0.5, tolerance: 4 });
  
  // Capas Base
  const baseLayers = {
    "OpenStreetMap (Voyager - Predeterminado)": L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png', {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions" target="_blank">CARTO</a>'
    }),
    "ESRI Calles del Mundo": L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}', {
      maxZoom: 19,
      attribution: 'Tiles &copy; Esri &mdash; Source: Esri, DeLorme, NAVTEQ, USGS, Intermap, iPC, NRCAN, Esri Japan, METI, Esri China (Hong Kong), Esri (Thailand), TomTom'
    }),
    "CartoDB Claro": L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
      maxZoom: 19,
      attribution: '&copy; OpenStreetMap &copy; CARTO'
    }),
    "CartoDB Oscuro": L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
      maxZoom: 19,
      attribution: '&copy; OpenStreetMap &copy; CARTO'
    }),
    "Satélite (ESRI)": L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
      maxZoom: 19,
      attribution: 'Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community'
    })
  };
  
  baseLayers["OpenStreetMap (Voyager - Predeterminado)"].addTo(map);
  L.control.layers(baseLayers, null, { position: 'bottomright' }).addTo(map);
  
  // Capa para destacar la manzana seleccionada
  const highlightLayer = L.geoJSON(null, {
    style: {
      color: '#0284c7',
      weight: 3.5,
      fillColor: '#38bdf8',
      fillOpacity: 0.85,
      dashArray: '4, 4'
    }
  }).addTo(map);

  // Paleta Áurea Determinística para Rutas (3.300 colores distintos)
  function getRouteColor(routeId) {
    if (!routeId || routeId === 0) return '#64748b';
    const hue = (routeId * 137.507764) % 360;
    return `hsl(${hue.toFixed(1)}, 84%, 55%)`;
  }
  
  // Paleta de 20 Ciclos de Facturación
  const cyclePalette = [
    '#f43f5e', '#ec4899', '#d946ef', '#a855f7', '#8b5cf6',
    '#6366f1', '#3b82f6', '#0ea5e9', '#06b6d4', '#14b8a6',
    '#10b981', '#22c55e', '#84cc16', '#eab308', '#f59e0b',
    '#f97316', '#ef4444', '#78716c', '#0284c7', '#4f46e5'
  ];
  
  function getCycleColor(cycleStr) {
    const num = parseInt(cycleStr, 10);
    if (isNaN(num)) return '#94a3b8';
    return cyclePalette[(num - 1) % cyclePalette.length];
  }
  
  function getDensityColor(sumis) {
    if (sumis <= 10) return '#38bdf8';
    if (sumis <= 30) return '#34d399';
    if (sumis <= 70) return '#fbbf24';
    if (sumis <= 150) return '#f97316';
    return '#ef4444'; // Macro-manzana
  }
  
  function getFeatureColor(props) {
    if (currentColorMode === 'cycle') return getCycleColor(props.g);
    if (currentColorMode === 'density') return getDensityColor(props.s);
    return getRouteColor(props.r);
  }
  
  // Capa Principal GeoJSON
  let geojsonLayer = null;
  let allFeatures = [];
  let featuresByMza = new Map();
  let featuresByRoute = new Map();

  function styleFeature(feature) {
    const props = feature.properties;
    const isIsolated = (activeIsolatedRoute !== null);
    const matchesIsolated = (props.r === activeIsolatedRoute);
    
    // Si hay una ruta aislada, atenuar fuertemente las demás
    if (isIsolated && !matchesIsolated) {
      return {
        renderer: canvasRenderer,
        fillColor: '#94a3b8',
        fillOpacity: 0.05,
        color: '#cbd5e1',
        weight: 0.3
      };
    }
    
    // Filtro por ciclo
    if (activeCycleFilter !== 'all' && props.g !== activeCycleFilter) {
      return {
        renderer: canvasRenderer,
        fillColor: 'transparent',
        fillOpacity: 0,
        color: 'transparent',
        weight: 0
      };
    }
    
    const color = getFeatureColor(props);
    return {
      renderer: canvasRenderer,
      fillColor: color,
      fillOpacity: isIsolated ? 0.88 : 0.68,
      color: isIsolated ? '#0f172a' : '#334155',
      weight: isIsolated ? 2.2 : 1.0
    };
  }

  function loadData(data) {
    allFeatures = data.features;
    
    const uniqueRoutes = new Set();
    const uniqueCycles = new Set();
    let totalSupplies = 0;
    
    allFeatures.forEach(feat => {
      const p = feat.properties;
      featuresByMza.set(p.m.toUpperCase(), feat);
      
      if (!featuresByRoute.has(p.r)) {
        featuresByRoute.set(p.r, []);
      }
      featuresByRoute.get(p.r).push(feat);
      
      uniqueRoutes.add(p.r);
      uniqueCycles.add(p.g);
      totalSupplies += p.s;
    });
    
    if (kpiMzas) kpiMzas.textContent = allFeatures.length.toLocaleString('es-AR');
    if (kpiRutas) kpiRutas.textContent = uniqueRoutes.size.toLocaleString('es-AR');
    if (kpiSumis) kpiSumis.textContent = totalSupplies.toLocaleString('es-AR');
    
    if (cycleSelect) {
      cycleSelect.innerHTML = '<option value="all">Todos los Ciclos</option>';
      const sortedCycles = Array.from(uniqueCycles).sort((a, b) => parseInt(a) - parseInt(b));
      sortedCycles.forEach(c => {
        const opt = document.createElement('option');
        opt.value = c;
        opt.textContent = `Ciclo ${c}`;
        cycleSelect.appendChild(opt);
      });
    }
    
    geojsonLayer = L.geoJSON(data, {
      renderer: canvasRenderer,
      style: styleFeature,
      onEachFeature: (feature, layer) => {
        layer.on({
          click: (e) => {
            L.DomEvent.stopPropagation(e);
            selectFeature(feature);
          },
          mouseover: (e) => {
            const p = feature.properties;
            layer.bindTooltip(`
              <div style="font-weight:700; color:#38bdf8; margin-bottom:2px;">Ruta ${p.r} (Ciclo ${p.g})</div>
              <div style="font-size:0.75rem; color:#e2e8f0;">Mza: ${p.m}</div>
              <div style="font-size:0.75rem; color:#94a3b8;">${p.s} suministros</div>
            `, {
              className: 'custom-tooltip',
              sticky: true,
              direction: 'top'
            }).openTooltip();
          }
        });
      }
    }).addTo(map);
    
    if (loadingOverlay) {
      loadingOverlay.classList.add('hidden');
    }
  }

  function selectFeature(feature) {
    currentSelectedFeature = feature;
    const p = feature.properties;
    
    highlightLayer.clearLayers();
    highlightLayer.addData(feature);
    
    if (inspMza) inspMza.textContent = p.m;
    if (inspRutaBadge) {
      inspRutaBadge.textContent = `Ruta ${p.r}`;
      inspRutaBadge.style.background = getRouteColor(p.r);
    }
    if (inspGrupo) inspGrupo.textContent = `Ciclo ${p.g}`;
    if (inspSumis) inspSumis.textContent = `${p.s.toLocaleString('es-AR')} suministros`;
    if (inspFuente) inspFuente.textContent = p.f || 'IDECOR';
    
    if (inspCalles) {
      inspCalles.innerHTML = '';
      if (p.c && p.c.trim() !== '') {
        const streets = p.c.split('|').map(s => s.trim()).filter(s => s.length > 0);
        streets.forEach(street => {
          const tag = document.createElement('span');
          tag.className = 'street-tag';
          tag.textContent = street;
          inspCalles.appendChild(tag);
        });
      } else {
        inspCalles.innerHTML = '<span style="color:var(--text-muted); font-size:0.75rem;">Sin calles catalogadas</span>';
      }
    }
    
    if (inspAlturas) {
      if (p.a && p.a.trim() !== '') {
        inspAlturas.textContent = p.a.split(';').slice(0, 4).join('; ');
      } else {
        inspAlturas.textContent = 'N/D';
      }
    }
    
    if (inspectorPanel) {
      inspectorPanel.classList.add('open');
    }
  }

  // Función Principal: Borrar Selección y Filtros de Manzanas / Rutas
  function clearAllSelectionsAndFilters() {
    currentSelectedFeature = null;
    activeIsolatedRoute = null;
    activeCycleFilter = 'all';
    
    if (cycleSelect) cycleSelect.value = 'all';
    if (searchInput) searchInput.value = '';
    
    highlightLayer.clearLayers();
    
    if (inspectorPanel) {
      inspectorPanel.classList.remove('open');
    }
    
    if (filterStatusBadge) {
      filterStatusBadge.classList.add('hidden');
    }
    
    if (geojsonLayer) {
      geojsonLayer.setStyle(styleFeature);
    }
  }

  // Aislar Ruta Completa
  if (btnIsolateRoute) {
    btnIsolateRoute.addEventListener('click', () => {
      if (!currentSelectedFeature) return;
      const targetRoute = currentSelectedFeature.properties.r;
      activeIsolatedRoute = targetRoute;
      
      const routeFeats = featuresByRoute.get(targetRoute) || [];
      
      // Mostrar Badge de filtro activo en barra superior
      if (filterStatusBadge && filterStatusText) {
        filterStatusText.textContent = `Ruta ${targetRoute} (${routeFeats.length} mzas)`;
        filterStatusBadge.classList.remove('hidden');
      }
      
      geojsonLayer.setStyle(styleFeature);
      
      if (routeFeats.length > 0) {
        const bounds = L.geoJSON({ type: 'FeatureCollection', features: routeFeats }).getBounds();
        map.fitBounds(bounds, { padding: [60, 60], maxZoom: 17 });
      }
    });
  }

  // Deseleccionar Manzana / Quitar Filtro en Inspector
  if (btnDeselectMza) {
    btnDeselectMza.addEventListener('click', () => {
      clearAllSelectionsAndFilters();
    });
  }

  // Botón Borrar Filtro en Barra Superior
  if (btnCleanFilter) {
    btnCleanFilter.addEventListener('click', () => {
      clearAllSelectionsAndFilters();
    });
  }

  // Botón Quitar Filtro en Badge Activo
  if (btnRemoveFilterBadge) {
    btnRemoveFilterBadge.addEventListener('click', () => {
      clearAllSelectionsAndFilters();
    });
  }

  // Botón Borrar en Barra Flotante
  if (btnFloatClear) {
    btnFloatClear.addEventListener('click', () => {
      clearAllSelectionsAndFilters();
    });
  }

  // Cerrar Inspector
  if (inspectorClose) {
    inspectorClose.addEventListener('click', () => {
      inspectorPanel.classList.remove('open');
      highlightLayer.clearLayers();
    });
  }

  // Restablecer Vista General
  if (btnResetView) {
    btnResetView.addEventListener('click', () => {
      clearAllSelectionsAndFilters();
      map.setView([-31.4201, -64.1888], 13);
    });
  }

  // Botones de Navegación y Zoom
  if (btnZoomIn) {
    btnZoomIn.addEventListener('click', () => {
      map.zoomIn();
    });
  }

  if (btnZoomOut) {
    btnZoomOut.addEventListener('click', () => {
      map.zoomOut();
    });
  }

  if (btnFitDistrict) {
    btnFitDistrict.addEventListener('click', () => {
      if (geojsonLayer) {
        map.fitBounds(geojsonLayer.getBounds(), { padding: [25, 25] });
      } else {
        map.setView([-31.4201, -64.1888], 13);
      }
    });
  }

  // Soporte nativo para Ctrl + Scroll del mouse (Zoom In / Out preciso)
  const mapContainer = document.getElementById('map');
  if (mapContainer) {
    mapContainer.addEventListener('wheel', (e) => {
      if (e.ctrlKey) {
        e.preventDefault(); // Previene el escalado del navegador web
        if (e.deltaY < 0) {
          map.zoomIn(1);
        } else if (e.deltaY > 0) {
          map.zoomOut(1);
        }
      }
    }, { passive: false });
  }

  // Atajos de Teclado (+, -, Esc)
  window.addEventListener('keydown', (e) => {
    // Si el usuario no está escribiendo en el buscador
    if (document.activeElement === searchInput) return;
    
    if (e.key === 'Escape') {
      clearAllSelectionsAndFilters();
    } else if (e.key === '+' || e.key === '=') {
      map.zoomIn();
    } else if (e.key === '-' || e.key === '_') {
      map.zoomOut();
    }
  });

  // Clic en área vacía del mapa deselecciona la manzana
  map.on('click', () => {
    if (currentSelectedFeature && activeIsolatedRoute === null) {
      currentSelectedFeature = null;
      highlightLayer.clearLayers();
      if (inspectorPanel) inspectorPanel.classList.remove('open');
    }
  });

  // Filtro por Ciclo
  if (cycleSelect) {
    cycleSelect.addEventListener('change', (e) => {
      activeCycleFilter = e.target.value;
      activeIsolatedRoute = null;
      
      if (filterStatusBadge && filterStatusText) {
        if (activeCycleFilter !== 'all') {
          filterStatusText.textContent = `Ciclo ${activeCycleFilter}`;
          filterStatusBadge.classList.remove('hidden');
        } else {
          filterStatusBadge.classList.add('hidden');
        }
      }
      
      geojsonLayer.setStyle(styleFeature);
      
      if (activeCycleFilter !== 'all') {
        const cycleFeats = allFeatures.filter(f => f.properties.g === activeCycleFilter);
        if (cycleFeats.length > 0) {
          const bounds = L.geoJSON({ type: 'FeatureCollection', features: cycleFeats }).getBounds();
          map.fitBounds(bounds, { padding: [40, 40] });
        }
      }
    });
  }

  // Modo de Color
  if (colorModeSelect) {
    colorModeSelect.addEventListener('change', (e) => {
      currentColorMode = e.target.value;
      geojsonLayer.setStyle(styleFeature);
    });
  }

  // Buscador Instantáneo (por Ruta, Manzana o Calle)
  if (searchInput) {
    searchInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        const query = searchInput.value.trim().toUpperCase();
        if (!query) return;
        
        // 1. Buscar por Ruta (ej. "1042" o "RUTA 1042")
        const routeMatch = query.replace('RUTA', '').trim();
        const routeNum = parseInt(routeMatch, 10);
        if (!isNaN(routeNum) && featuresByRoute.has(routeNum)) {
          const routeFeats = featuresByRoute.get(routeNum);
          activeIsolatedRoute = routeNum;
          
          if (filterStatusBadge && filterStatusText) {
            filterStatusText.textContent = `Ruta ${routeNum} (${routeFeats.length} mzas)`;
            filterStatusBadge.classList.remove('hidden');
          }
          
          geojsonLayer.setStyle(styleFeature);
          selectFeature(routeFeats[0]);
          const bounds = L.geoJSON({ type: 'FeatureCollection', features: routeFeats }).getBounds();
          map.fitBounds(bounds, { padding: [60, 60], maxZoom: 17 });
          return;
        }
        
        // 2. Buscar por ID de Manzana
        if (featuresByMza.has(query)) {
          const feat = featuresByMza.get(query);
          selectFeature(feat);
          const bounds = L.geoJSON(feat).getBounds();
          map.fitBounds(bounds, { padding: [80, 80], maxZoom: 18 });
          return;
        }
        
        // 3. Buscar parcial por Manzana o Calle
        const partial = allFeatures.find(f => f.properties.m.includes(query) || f.properties.c.toUpperCase().includes(query));
        if (partial) {
          selectFeature(partial);
          const bounds = L.geoJSON(partial).getBounds();
          map.fitBounds(bounds, { padding: [80, 80], maxZoom: 18 });
          return;
        }
        
        alert(`No se encontró ninguna manzana o ruta para "${query}". Intente con un número de ruta (ej. 1042) o código catastral.`);
      }
    });
  }

  // Carga de Datos: Usa el script embebido window.MANZANAS_DATA o fetch GeoJSON
  if (typeof MANZANAS_DATA !== 'undefined') {
    if (loadingText) loadingText.textContent = 'Renderizando 18.721 manzanas catastrales en Canvas...';
    setTimeout(() => {
      loadData(MANZANAS_DATA);
    }, 100);
  } else {
    if (loadingText) loadingText.textContent = 'Descargando GeoJSON de manzanas (15.4 MB)...';
    fetch('data/manzanas_rutas_distrito1.geojson')
      .then(res => res.json())
      .then(data => {
        loadData(data);
      })
      .catch(err => {
        console.error('Error cargando GeoJSON:', err);
        if (loadingText) loadingText.innerHTML = `Error cargando archivo de datos.<br><span style="font-size:0.75rem; color:#ef4444;">${err.message}</span>`;
      });
  }
});
