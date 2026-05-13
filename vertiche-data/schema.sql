create table if not exists estados (
  id     serial primary key,
  nombre text unique not null
);

create table if not exists municipios (
  id        serial primary key,
  estado_id int references estados(id) on delete cascade,
  nombre    text not null,
  unique (estado_id, nombre)
);

create table if not exists tramites (
  id                    serial primary key,
  municipio_id          int references municipios(id) on delete cascade,
  doc_tipo              text not null,
  homoclave             text,
  nombre_tramite        text,
  descripcion           text,
  dependencia           text,
  modalidad             text,
  vigencia              text,
  costo                 text,
  tiempo_respuesta      text,
  afirmativa_ficta      boolean default false,
  url_fuente            text,
  fecha_actualizacion   text,
  fecha_scrape          timestamptz default now(),
  raw_text              text
);

create table if not exists requisitos (
  id           serial primary key,
  tramite_id   int references tramites(id) on delete cascade,
  orden        int,
  texto        text not null,
  presentacion text,
  num_copias   int,
  obligatorio  boolean default true,
  condicion    text
);

create table if not exists ubicaciones (
  id          serial primary key,
  tramite_id  int references tramites(id) on delete cascade,
  nombre      text,
  direccion   text,
  telefono    text,
  horario     text,
  dias        text
);

create table if not exists scraper_errores (
  id          serial primary key,
  estado      text,
  municipio   text,
  doc_tipo    text,
  url         text,
  mensaje     text,
  fecha       timestamptz default now(),
  reintentado boolean default false
);

create index if not exists idx_tramites_doc_tipo  on tramites(doc_tipo);
create index if not exists idx_tramites_municipio on tramites(municipio_id);
create index if not exists idx_requisitos_tramite on requisitos(tramite_id);

create table if not exists tienda_permisos (
  id             serial primary key,
  tienda_nombre  text not null,          
  municipio      text not null,
  doc_tipo       text not null,          
  permiso_nombre text,                   
  vigencia_2025  text,                  
  vigencia_2026  text,
  fecha_carga    timestamptz default now(),
  unique (tienda_id, doc_tipo)
);

create index if not exists idx_tienda_permisos_tienda   on tienda_permisos(tienda_id);
create index if not exists idx_tienda_permisos_doc_tipo on tienda_permisos(doc_tipo);
