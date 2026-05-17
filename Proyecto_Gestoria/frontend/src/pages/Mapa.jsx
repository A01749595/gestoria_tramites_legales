import { useEffect, useMemo, useState } from "react";
import { MapContainer, TileLayer, CircleMarker, Popup } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import { useNavigate } from "react-router-dom";
import { getDashboard } from "../services/api";

const coordsByState = {
  "Ciudad de México": [19.4326, -99.1332], 
  "Nuevo León": [25.6866, -100.3161], 
  "Jalisco": [20.6597, -103.3496], 
  "Puebla": [19.0414, -98.2063],
  "Baja California": [32.5149, -117.0382], 
  "Yucatán": [20.9674, -89.5926], 
  "Guanajuato": [21.019, -101.2574], 
  "México": [19.35, -99.65],
  "Querétaro": [20.5888, -100.3899], 
  "Veracruz": [19.1738, -96.1342], 
  "Chihuahua": [28.632, -106.0691], 
  "Sonora": [29.0729, -110.9559],
  "Coahuila": [25.4232, -101.0053], 
  "Sinaloa": [24.8091, -107.394], 
  "Oaxaca": [17.0732, -96.7266], 
  "Quintana Roo": [21.1619, -86.8515],
};


function scoreColor(score) {
  if (score >= 80) return "#07ac17";
  if (score >= 55) return "#F59E0B";
  return "#d70f0f";
}


export default function Mapa() {
  const [branches, setBranches] = useState([]);
  const [scores, setScores] = useState({});
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    getDashboard(false).then((res) => {
      setBranches(res.data?.branches || []);
      setScores(res.data?.compliance_scores || {});
    }).finally(() => setLoading(false));
  }, []);

  const points = useMemo(() => branches.map((b, i) => {
    const base = coordsByState[b.state] || [23.6345, -102.5528];
    return { ...b, lat: base[0] + (i % 5) * 0.08, lng: base[1] + (i % 5) * 0.08, score: scores[b.branch_id] || 0 };
  }), [branches, scores]);

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Mapa de sucursales</h1>
          <p className="page-sub">Ubicación aproximada por estado con score de cumplimiento.
            </p>
          </div>
        </div>
      <div className="card map-card">
        {loading ? <p>Cargando mapa...</p> : (
          <MapContainer 
            center={[23.6345, -102.5528]} 
            zoom={5} 
            style={{ height: "620px", width: "100%", borderRadius: "10px" }}
            >
            <TileLayer 
              attribution="&copy; OpenStreetMap" 
              url="https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png" 
              />
            {points.map((p) => (
              <CircleMarker 
                key={p.branch_id} 
                center={[p.lat, p.lng]} 
                radius={10 + Math.min(p.score, 100) / 12} 
                pathOptions={{ 
                  fillColor: scoreColor(p.score),
                  fillOpacity: 0.9,
                  color: "#08292dd1",
                  weight: 1.5,
                }}
                >
                <Popup>
                  <strong>
                    {p.branch_name}
                    </strong>
                    <br/>
                    {p.state} · {p.municipality}
                    <br/>
                    Score: {p.score}%
                    <br/>
                  <button onClick={() => navigate(`/sucursal/${p.branch_id}`)}>Ver detalle</button>
                </Popup>
              </CircleMarker>
            ))}
          </MapContainer>
        )}
      </div>
    </div>
  );
}
