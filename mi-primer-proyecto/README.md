# Instalacion
Despues de clonar el reporsitorio:
npm install (para generar node_modules)

Iniciar la pagina: npm run dev



# GestiónDoc — Sistema de Gestión de Trámites

## Instalación de dependencias

Abre la terminal en VSCode (Ctrl + Ñ) y ejecuta:

```bash
npm install react-router-dom recharts lucide-react react-leaflet leaflet
```

## Levantar el proyecto

```bash
npm run dev
```

Abre http://localhost:5173

---

## Estructura del proyecto

```
src/
├── pages/
│   ├── Dashboard.jsx     → KPIs, gráfica y alertas recientes
│   ├── Mapa.jsx          → Mapa interactivo con sucursales
│   ├── Sucursal.jsx      → Detalle de trámites por sucursal (con score)
│   └── Documentos.jsx    → Carga y validación de documentos
├── components/
│   ├── Navbar.jsx        → Barra lateral de navegación
│   ├── KpiCard.jsx       → Tarjeta de KPI reutilizable
│   ├── TramiteCard.jsx   → Tarjeta de trámite con barra de progreso
│   └── UploadZone.jsx    → Zona de drag & drop para documentos
├── data/
│   └── mockData.js       → Datos de prueba (se reemplaza con llamadas a la API)
├── App.jsx               → Rutas principales
├── main.jsx              → Entry point
└── index.css             → Estilos globales
```

---

## Cómo conectar con el backend (FastAPI)

Cuando tu backend esté listo, reemplaza los datos de `mockData.js` con llamadas reales.

### Ejemplo: Dashboard KPIs

**Antes (mock):**
```javascript
import { kpis } from "../data/mockData";
```

**Después (API real):**
```javascript
const [kpis, setKpis] = useState([]);

useEffect(() => {
  fetch("http://localhost:8000/kpis")
    .then(res => res.json())
    .then(data => setKpis(data));
}, []);
```

### Endpoints que necesitarás crear en FastAPI

| Página | Método | Endpoint sugerido |
|--------|--------|-------------------|
| Dashboard | GET | /kpis |
| Dashboard | GET | /alertas |
| Mapa | GET | /sucursales |
| Sucursal | GET | /sucursales/{id}/tramites |
| Documentos | POST | /documentos/validar |
| Alertas | POST | /alertas/enviar |

---

## Sistema de alertas (correo)

Se implementará en el backend con:
- **FastAPI** para los endpoints
- **FastAPI Background Tasks** o **APScheduler** para revisar fechas de vencimiento
- **smtplib** o **fastapi-mail** para enviar correos
