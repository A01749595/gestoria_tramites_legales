"""
Datos semilla de trámites por sucursal — extraídos de TRAMITES.docx
(Comercial IAC SA de CV).

Cada sucursal tiene una lista de permisos. Los 5 trámites base que
aplican a TODAS las sucursales son:
  1. Aviso de funcionamiento
  2. Uso de suelo
  3. Anuncio
  4. Protección Civil (Visto Bueno)
  5. Licencia Ambiental

Algunas sucursales tienen permisos extra (dictámenes de bomberos, etc.).
Este archivo solo se usa para PRECARGAR el tab de llenado manual la
primera vez. Una vez el usuario guarda, los datos viven en el JSON
en disco (tramites_data.json) y este archivo ya no se consulta.
"""

import json

# Los 5 trámites obligatorios sobre los que se calcula el % de cumplimiento.
TRAMITES_REQUERIDOS = [
    "Aviso de funcionamiento",
    "Uso de suelo",
    "Anuncio",
    "Protección Civil Visto Bueno",
    "Licencia Ambiental",
]

# Cargamos la semilla desde un string JSON embebido (evita problemas de
# escapado con literales Python).
_SEED_JSON = r"""
[
  {
    "tramite_id": "T-001",
    "nombre": "San Antonio Abad",
    "permisos": [
      {
        "no": "1",
        "permiso": "Aviso de funcionamiento",
        "vigencia_2025": "Permanente",
        "vigencia_2026": "Permanente"
      },
      {
        "no": "2",
        "permiso": "Uso de suelo",
        "vigencia_2025": "Sin trámite",
        "vigencia_2026": "Sin trámite"
      },
      {
        "no": "3",
        "permiso": "Anuncio",
        "vigencia_2025": "Sin trámite",
        "vigencia_2026": "Sin trámite"
      },
      {
        "no": "4",
        "permiso": "Protección Civil",
        "vigencia_2025": "Vo Bo",
        "vigencia_2026": "Vo Bo"
      },
      {
        "no": "5",
        "permiso": "Licencia Ambiental",
        "vigencia_2025": "",
        "vigencia_2026": ""
      }
    ]
  },
  {
    "tramite_id": "T-003",
    "nombre": "Portales",
    "permisos": [
      {
        "no": "1",
        "permiso": "Aviso de funcionamiento",
        "vigencia_2025": "Permanente",
        "vigencia_2026": "Permanente"
      },
      {
        "no": "2",
        "permiso": "Uso de suelo",
        "vigencia_2025": "18/03/2026",
        "vigencia_2026": "Pendiente"
      },
      {
        "no": "3",
        "permiso": "Anuncio",
        "vigencia_2025": "Sin trámite",
        "vigencia_2026": "Sin trámite"
      },
      {
        "no": "4",
        "permiso": "Protección Civil",
        "vigencia_2025": "No aplica",
        "vigencia_2026": "No aplica"
      },
      {
        "no": "5",
        "permiso": "Licencia Ambiental",
        "vigencia_2025": "",
        "vigencia_2026": ""
      }
    ]
  },
  {
    "tramite_id": "T-007",
    "nombre": "Tlanepantla",
    "permisos": [
      {
        "no": "1",
        "permiso": "Aviso de funcionamiento",
        "vigencia_2025": "Permanente",
        "vigencia_2026": "Permanente"
      },
      {
        "no": "2",
        "permiso": "Uso de suelo",
        "vigencia_2025": "No aplica",
        "vigencia_2026": "No aplica"
      },
      {
        "no": "3",
        "permiso": "Anuncio",
        "vigencia_2025": "31/12/2025",
        "vigencia_2026": "Pagado"
      },
      {
        "no": "4",
        "permiso": "Protección Civil Visto Bueno",
        "vigencia_2025": "19/05/2026",
        "vigencia_2026": ""
      },
      {
        "no": "5",
        "permiso": "Licencia Ambiental",
        "vigencia_2025": "",
        "vigencia_2026": ""
      }
    ]
  },
  {
    "tramite_id": "T-008",
    "nombre": "Chalco",
    "permisos": [
      {
        "no": "1",
        "permiso": "Aviso de funcionamiento",
        "vigencia_2025": "31/12/2025",
        "vigencia_2026": ""
      },
      {
        "no": "2",
        "permiso": "Uso de suelo",
        "vigencia_2025": "No aplica",
        "vigencia_2026": "No aplica"
      },
      {
        "no": "3",
        "permiso": "Anuncio",
        "vigencia_2025": "31/12/2025",
        "vigencia_2026": "Pagado"
      },
      {
        "no": "4",
        "permiso": "Protección Civil Visto Bueno",
        "vigencia_2025": "31/12/2025",
        "vigencia_2026": "Pagado"
      },
      {
        "no": "5",
        "permiso": "Licencia Ambiental",
        "vigencia_2025": "",
        "vigencia_2026": ""
      }
    ]
  },
  {
    "tramite_id": "T-014",
    "nombre": "Puebla Outlet",
    "permisos": [
      {
        "no": "1",
        "permiso": "Aviso de funcionamiento",
        "vigencia_2025": "21/12/2025",
        "vigencia_2026": "31/12/2026"
      },
      {
        "no": "2",
        "permiso": "Uso de suelo",
        "vigencia_2025": "10/01/2026",
        "vigencia_2026": "11/02/2027"
      },
      {
        "no": "3",
        "permiso": "Anuncio",
        "vigencia_2025": "Sin trámite",
        "vigencia_2026": "31/12/2026"
      },
      {
        "no": "4",
        "permiso": "Protección Civil Visto Bueno",
        "vigencia_2025": "20/02/2026",
        "vigencia_2026": "27/02/2027"
      },
      {
        "no": "5",
        "permiso": "Dictamen de medidas contra incendio",
        "vigencia_2025": "20/02/2026",
        "vigencia_2026": "27/02/2027"
      },
      {
        "no": "6",
        "permiso": "Licencia Ambiental",
        "vigencia_2025": "",
        "vigencia_2026": ""
      },
      {
        "no": "7",
        "permiso": "Alineamiento y No oficial",
        "vigencia_2025": "27/11/2025",
        "vigencia_2026": "11/02/2027"
      }
    ]
  },
  {
    "tramite_id": "T-015",
    "nombre": "Atlixco",
    "permisos": [
      {
        "no": "1",
        "permiso": "Aviso de funcionamiento",
        "vigencia_2025": "31/12/2025",
        "vigencia_2026": "Pagado"
      },
      {
        "no": "2",
        "permiso": "Uso de suelo",
        "vigencia_2025": "Permanente",
        "vigencia_2026": "Permanente"
      },
      {
        "no": "3",
        "permiso": "Anuncio",
        "vigencia_2025": "Sin tramite",
        "vigencia_2026": "Sin tramite"
      },
      {
        "no": "4",
        "permiso": "Protección Civil Visto Bueno",
        "vigencia_2025": "06/02/2026",
        "vigencia_2026": "Pagado"
      },
      {
        "no": "5",
        "permiso": "Dictamen Bomberos",
        "vigencia_2025": "06/02/2026",
        "vigencia_2026": "Pagado"
      },
      {
        "no": "6",
        "permiso": "Licencia Ambiental",
        "vigencia_2025": "",
        "vigencia_2026": ""
      }
    ]
  },
  {
    "tramite_id": "T-016",
    "nombre": "Puebla",
    "permisos": [
      {
        "no": "1",
        "permiso": "Aviso de funcionamiento",
        "vigencia_2025": "Permanente",
        "vigencia_2026": "Permanente"
      },
      {
        "no": "2",
        "permiso": "Uso de suelo",
        "vigencia_2025": "Permanente",
        "vigencia_2026": "Permanente"
      },
      {
        "no": "3",
        "permiso": "Factibilidad de uso de suelo centro histórico",
        "vigencia_2025": "Sin trámite",
        "vigencia_2026": "Permanente"
      },
      {
        "no": "4",
        "permiso": "Anuncio",
        "vigencia_2025": "Sin trámite",
        "vigencia_2026": "Sin tramite"
      },
      {
        "no": "5",
        "permiso": "Protección Civil Visto Bueno",
        "vigencia_2025": "16/10/2026",
        "vigencia_2026": ""
      },
      {
        "no": "6",
        "permiso": "Dictamen Bomberos",
        "vigencia_2025": "06/11/2026",
        "vigencia_2026": ""
      },
      {
        "no": "7",
        "permiso": "Licencia Ambiental",
        "vigencia_2025": "",
        "vigencia_2026": ""
      }
    ]
  },
  {
    "tramite_id": "T-017",
    "nombre": "Izúcar",
    "permisos": [
      {
        "no": "1",
        "permiso": "Aviso de funcionamiento",
        "vigencia_2025": "31/12/2025",
        "vigencia_2026": ""
      },
      {
        "no": "2",
        "permiso": "Uso de suelo",
        "vigencia_2025": "31/12/2025",
        "vigencia_2026": "31/12/2026"
      },
      {
        "no": "3",
        "permiso": "Anuncio",
        "vigencia_2025": "31/12/2025",
        "vigencia_2026": "31/12/2026"
      },
      {
        "no": "4",
        "permiso": "Protección Civil Visto Bueno",
        "vigencia_2025": "31/12/2025",
        "vigencia_2026": "31/12/2026"
      },
      {
        "no": "5",
        "permiso": "Licencia Ambiental",
        "vigencia_2025": "",
        "vigencia_2026": ""
      }
    ]
  },
  {
    "tramite_id": "T-018",
    "nombre": "Huamantla",
    "permisos": [
      {
        "no": "1",
        "permiso": "Aviso de funcionamiento",
        "vigencia_2025": "31/12/2025",
        "vigencia_2026": ""
      },
      {
        "no": "2",
        "permiso": "Uso de suelo",
        "vigencia_2025": "31/12/2025",
        "vigencia_2026": ""
      },
      {
        "no": "3",
        "permiso": "Anuncio",
        "vigencia_2025": "Sin trámite",
        "vigencia_2026": ""
      },
      {
        "no": "4",
        "permiso": "Protección Civil Visto Bueno",
        "vigencia_2025": "31/12/2025",
        "vigencia_2026": ""
      },
      {
        "no": "5",
        "permiso": "Licencia Ambiental",
        "vigencia_2025": "",
        "vigencia_2026": ""
      }
    ]
  },
  {
    "tramite_id": "T-019",
    "nombre": "Orizaba",
    "permisos": [
      {
        "no": "1",
        "permiso": "Aviso de funcionamiento",
        "vigencia_2025": "31/12/2025",
        "vigencia_2026": ""
      },
      {
        "no": "2",
        "permiso": "Uso de suelo",
        "vigencia_2025": "31/12/2025",
        "vigencia_2026": ""
      },
      {
        "no": "3",
        "permiso": "Anuncio",
        "vigencia_2025": "31/12/2025",
        "vigencia_2026": "31/12/2016"
      },
      {
        "no": "4",
        "permiso": "Protección Civil Visto Bueno",
        "vigencia_2025": "22/11/2027",
        "vigencia_2026": ""
      },
      {
        "no": "5",
        "permiso": "Convenio de bomberos",
        "vigencia_2025": "09/10/2026",
        "vigencia_2026": ""
      },
      {
        "no": "6",
        "permiso": "Licencia ambiental",
        "vigencia_2025": "",
        "vigencia_2026": ""
      }
    ]
  },
  {
    "tramite_id": "T-022",
    "nombre": "Veracruz",
    "permisos": [
      {
        "no": "1",
        "permiso": "Aviso de funcionamiento",
        "vigencia_2025": "Permanente",
        "vigencia_2026": "Permanente"
      },
      {
        "no": "2",
        "permiso": "Uso de suelo",
        "vigencia_2025": "07/11/2026",
        "vigencia_2026": ""
      },
      {
        "no": "3",
        "permiso": "Anuncio",
        "vigencia_2025": "Sin trámite",
        "vigencia_2026": ""
      },
      {
        "no": "4",
        "permiso": "Protección Civil Visto Bueno",
        "vigencia_2025": "12/12/2026",
        "vigencia_2026": ""
      },
      {
        "no": "5",
        "permiso": "Licencia Ambiental",
        "vigencia_2025": "",
        "vigencia_2026": ""
      }
    ]
  },
  {
    "tramite_id": "T-023",
    "nombre": "Chilpancingo",
    "permisos": [
      {
        "no": "1",
        "permiso": "Aviso de funcionamiento",
        "vigencia_2025": "31/12/2025",
        "vigencia_2026": "31/12/2026"
      },
      {
        "no": "2",
        "permiso": "Uso de suelo",
        "vigencia_2025": "Permanente",
        "vigencia_2026": "Permanente"
      },
      {
        "no": "3",
        "permiso": "Anuncio",
        "vigencia_2025": "31/12/2025",
        "vigencia_2026": "31/12/2026"
      },
      {
        "no": "4",
        "permiso": "Protección Civil Visto Bueno",
        "vigencia_2025": "31/12/2025",
        "vigencia_2026": "31/12/2026"
      },
      {
        "no": "5",
        "permiso": "Dictamen de bomberos",
        "vigencia_2025": "31/12/2025",
        "vigencia_2026": "31/12/2026"
      },
      {
        "no": "6",
        "permiso": "Dictamen de regulación de niveles máximos de sonido",
        "vigencia_2025": "31/12/2025",
        "vigencia_2026": "31/12/2026"
      },
      {
        "no": "7",
        "permiso": "Licencia ambiental",
        "vigencia_2025": "31/12/2025",
        "vigencia_2026": "31/12/2026"
      }
    ]
  },
  {
    "tramite_id": "T-024",
    "nombre": "Zamora",
    "permisos": [
      {
        "no": "1",
        "permiso": "Aviso de funcionamiento",
        "vigencia_2025": "31/12/2025",
        "vigencia_2026": "31/12/2025"
      },
      {
        "no": "2",
        "permiso": "Uso de suelo",
        "vigencia_2025": "No aplica",
        "vigencia_2026": "No aplica"
      },
      {
        "no": "3",
        "permiso": "Anuncio",
        "vigencia_2025": "31/12/2025",
        "vigencia_2026": "31/12/2025"
      },
      {
        "no": "4",
        "permiso": "Protección Civil Visto Bueno",
        "vigencia_2025": "24/11/2026",
        "vigencia_2026": ""
      },
      {
        "no": "5",
        "permiso": "Aprobación del Programa de Protección C",
        "vigencia_2025": "24/11/2026",
        "vigencia_2026": ""
      },
      {
        "no": "6",
        "permiso": "Licencia Ambiental",
        "vigencia_2025": "",
        "vigencia_2026": ""
      }
    ]
  },
  {
    "tramite_id": "T-025",
    "nombre": "Uruapan",
    "permisos": [
      {
        "no": "1",
        "permiso": "Aviso de funcionamiento",
        "vigencia_2025": "31/12/2025",
        "vigencia_2026": "31/12/2026"
      },
      {
        "no": "2",
        "permiso": "Uso de suelo",
        "vigencia_2025": "No aplica",
        "vigencia_2026": "No aplica"
      },
      {
        "no": "3",
        "permiso": "Anuncio",
        "vigencia_2025": "31/12/2025",
        "vigencia_2026": "31/12/2026"
      },
      {
        "no": "4",
        "permiso": "Protección Civil Visto Bueno",
        "vigencia_2025": "26/10/2026",
        "vigencia_2026": ""
      },
      {
        "no": "5",
        "permiso": "Licencia Ambiental",
        "vigencia_2025": "",
        "vigencia_2026": ""
      }
    ]
  },
  {
    "tramite_id": "T-028",
    "nombre": "Mérida",
    "permisos": [
      {
        "no": "1",
        "permiso": "Aviso de funcionamiento",
        "vigencia_2025": "",
        "vigencia_2026": ""
      },
      {
        "no": "2",
        "permiso": "Uso de suelo",
        "vigencia_2025": "",
        "vigencia_2026": ""
      },
      {
        "no": "3",
        "permiso": "Anuncio",
        "vigencia_2025": "",
        "vigencia_2026": ""
      },
      {
        "no": "4",
        "permiso": "Protección Civil Visto Bueno",
        "vigencia_2025": "22/09/2026",
        "vigencia_2026": ""
      },
      {
        "no": "5",
        "permiso": "Licencia Ambiental",
        "vigencia_2025": "",
        "vigencia_2026": ""
      }
    ]
  },
  {
    "tramite_id": "T-030",
    "nombre": "Tuxpan",
    "permisos": [
      {
        "no": "1",
        "permiso": "Aviso de funcionamiento",
        "vigencia_2025": "31/12/2025",
        "vigencia_2026": "31/12/2026"
      },
      {
        "no": "2",
        "permiso": "Cedula de empadronamiento",
        "vigencia_2025": "Sin trámite",
        "vigencia_2026": "31/12/2026"
      },
      {
        "no": "3",
        "permiso": "Uso de suelo",
        "vigencia_2025": "31/03/2026",
        "vigencia_2026": ""
      },
      {
        "no": "4",
        "permiso": "Anuncio",
        "vigencia_2025": "31/07/2026",
        "vigencia_2026": ""
      },
      {
        "no": "5",
        "permiso": "Protección Civil Visto Bueno",
        "vigencia_2025": "16/12/2025",
        "vigencia_2026": ""
      },
      {
        "no": "6",
        "permiso": "Licencia Ambiental",
        "vigencia_2025": "",
        "vigencia_2026": ""
      }
    ]
  },
  {
    "tramite_id": "T-032",
    "nombre": "Tuxtla Gutiérrez",
    "permisos": [
      {
        "no": "1",
        "permiso": "Aviso de funcionamiento",
        "vigencia_2025": "16/10/2026",
        "vigencia_2026": ""
      },
      {
        "no": "2",
        "permiso": "Uso de suelo",
        "vigencia_2025": "Permanente",
        "vigencia_2026": "Permanente"
      },
      {
        "no": "3",
        "permiso": "Anuncio",
        "vigencia_2025": "31/12/2025",
        "vigencia_2026": ""
      },
      {
        "no": "4",
        "permiso": "Protección Civil Visto Bueno",
        "vigencia_2025": "03/06/2025",
        "vigencia_2026": ""
      },
      {
        "no": "5",
        "permiso": "Licencia Ambiental",
        "vigencia_2025": "",
        "vigencia_2026": ""
      }
    ]
  },
  {
    "tramite_id": "T-034",
    "nombre": "Villa Hermosa",
    "permisos": [
      {
        "no": "1",
        "permiso": "Aviso de funcionamiento",
        "vigencia_2025": "31/12/2025",
        "vigencia_2026": ""
      },
      {
        "no": "2",
        "permiso": "Uso de suelo",
        "vigencia_2025": "",
        "vigencia_2026": ""
      },
      {
        "no": "3",
        "permiso": "Anuncio",
        "vigencia_2025": "",
        "vigencia_2026": ""
      },
      {
        "no": "4",
        "permiso": "Protección Civil Visto Bueno",
        "vigencia_2025": "22/10/2026",
        "vigencia_2026": ""
      },
      {
        "no": "5",
        "permiso": "Licencia Ambiental",
        "vigencia_2025": "",
        "vigencia_2026": ""
      }
    ]
  },
  {
    "tramite_id": "T-035",
    "nombre": "Cuautla Bravos",
    "permisos": [
      {
        "no": "1",
        "permiso": "Aviso de funcionamiento",
        "vigencia_2025": "31/12/2025",
        "vigencia_2026": "31/12/2026"
      },
      {
        "no": "2",
        "permiso": "Uso de suelo",
        "vigencia_2025": "Permanente",
        "vigencia_2026": "Permanente"
      },
      {
        "no": "3",
        "permiso": "Anuncio",
        "vigencia_2025": "31/12/2025",
        "vigencia_2026": "31/12/2026"
      },
      {
        "no": "4",
        "permiso": "Protección Civil Visto Bueno",
        "vigencia_2025": "31/12/2025",
        "vigencia_2026": "31/12/2026"
      },
      {
        "no": "5",
        "permiso": "Aprobación del programa de Protección C",
        "vigencia_2025": "31/12/2025",
        "vigencia_2026": "31/12/2026"
      },
      {
        "no": "6",
        "permiso": "Licencia Ambiental",
        "vigencia_2025": "",
        "vigencia_2026": ""
      }
    ]
  },
  {
    "tramite_id": "T-037",
    "nombre": "Apizaco",
    "permisos": [
      {
        "no": "1",
        "permiso": "Aviso de funcionamiento",
        "vigencia_2025": "",
        "vigencia_2026": ""
      },
      {
        "no": "2",
        "permiso": "Uso de suelo",
        "vigencia_2025": "",
        "vigencia_2026": ""
      },
      {
        "no": "3",
        "permiso": "Anuncio",
        "vigencia_2025": "",
        "vigencia_2026": ""
      },
      {
        "no": "4",
        "permiso": "Protección Civil Visto Bueno",
        "vigencia_2025": "31/12/2025",
        "vigencia_2026": ""
      },
      {
        "no": "5",
        "permiso": "Licencia Ambiental",
        "vigencia_2025": "31/12/2025",
        "vigencia_2026": ""
      }
    ]
  },
  {
    "tramite_id": "T-038",
    "nombre": "Toluca",
    "permisos": [
      {
        "no": "1",
        "permiso": "Aviso de funcionamiento",
        "vigencia_2025": "31/12/2025",
        "vigencia_2026": "Ingreso"
      },
      {
        "no": "2",
        "permiso": "Uso de suelo",
        "vigencia_2025": "No aplica",
        "vigencia_2026": "No aplica"
      },
      {
        "no": "3",
        "permiso": "Anuncio",
        "vigencia_2025": "31/12/2025",
        "vigencia_2026": ""
      },
      {
        "no": "4",
        "permiso": "Protección Civil Visto Bueno",
        "vigencia_2025": "12/08/2026",
        "vigencia_2026": ""
      },
      {
        "no": "5",
        "permiso": "Licencia Ambiental",
        "vigencia_2025": "",
        "vigencia_2026": ""
      }
    ]
  }
]
"""

TRAMITES_SEED = json.loads(_SEED_JSON)
