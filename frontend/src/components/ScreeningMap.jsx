import { useEffect, useRef } from 'react';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { STYLE, FALLBACK_STYLE } from './MapCard';

/* Where to go: the person's location (gold) and the recommended EHS facilities (blue, the
   first one larger). Same key-free basemap as the Geography map, same offline fallback. */
export default function ScreeningMap({ user, facilities = [], height = 220 }) {
  const elRef = useRef(null);
  const mapRef = useRef(null);
  const markersRef = useRef([]);

  useEffect(() => {
    if (!elRef.current || mapRef.current) return;
    const map = new maplibregl.Map({
      container: elRef.current, style: STYLE, center: [55.6, 25.4], zoom: 7.6,
      attributionControl: false, dragRotate: false,
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
    map.addControl(new maplibregl.AttributionControl({ compact: true }), 'bottom-right');
    let fell = false;
    map.on('load', () => { map.__ready = true; map.fire('scr:refresh'); });
    map.on('error', (e) => {
      if (!map.__ready && !fell && /style|fetch|load/i.test(String(e?.error?.message || ''))) {
        fell = true; map.setStyle(FALLBACK_STYLE);
      }
    });
    mapRef.current = map;
    return () => { map.remove(); mapRef.current = null; };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const apply = () => {
      markersRef.current.forEach((m) => m.remove());
      markersRef.current = [];
      const pts = [];
      facilities.forEach((f, i) => {
        const el = document.createElement('div');
        el.className = `scr-pin ${i === 0 ? 'first' : ''} ${f.endoscopy ? 'hosp' : ''}`;
        el.title = `${f.name} · ${f.km} km`;
        const m = new maplibregl.Marker({ element: el, anchor: 'center' }).setLngLat([f.lon, f.lat])
          .setPopup(new maplibregl.Popup({ closeButton: false, offset: 12, className: 'mc-popup' })
            .setHTML(`<div class="mc-pop-title">${f.name}</div><div class="mc-pop-row"><span class="mc-k">${f.type}</span>${f.km} km · about ${f.minutes} min</div>`))
          .addTo(map);
        markersRef.current.push(m);
        pts.push([f.lon, f.lat]);
      });
      if (user?.lat != null && user?.lon != null) {
        const el = document.createElement('div');
        el.className = 'scr-pin you';
        el.title = user.label || 'You';
        markersRef.current.push(new maplibregl.Marker({ element: el, anchor: 'center' }).setLngLat([user.lon, user.lat]).addTo(map));
        pts.push([user.lon, user.lat]);
      }
      if (pts.length === 1) map.easeTo({ center: pts[0], zoom: 11, duration: 600 });
      else if (pts.length > 1) {
        const b = pts.reduce((bb, p) => bb.extend(p), new maplibregl.LngLatBounds(pts[0], pts[0]));
        map.fitBounds(b, { padding: 44, maxZoom: 12, duration: 700 });
      }
    };
    if (map.__ready) apply(); else map.once('scr:refresh', apply);
  }, [user, facilities]);

  return <div className="mc-frame" style={{ height }}><div ref={elRef} className="mc-map" style={{ height: '100%' }} /></div>;
}
