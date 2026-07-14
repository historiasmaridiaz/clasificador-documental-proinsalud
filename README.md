# Gestión documental inteligente — PROINSALUD S.A.

Aplicación web local en Python y Streamlit para clasificar documentos con base en las Tablas de Retención Documental (TRD) y el Cuadro de Clasificación Documental (CCD) de PROINSALUD S.A.

Esta edición integra un módulo independiente para visualizar y descargar las TRD originales, el CCD por área y el organigrama; además conserva OCR local por página, clasificación híbrida, modo nocturno, revisión en vista completa y exportación de carpetas masivas.

## Catálogo institucional incluido

- 562 clasificaciones TRD/CCD normalizadas.
- 40 dependencias.
- 194 series.
- 529 subseries.
- 42 archivos fuente dentro de `data/fuentes_trd_proinsalud.zip`.
- Plantilla con 2.945 entradas de carpetas dentro de `data/plantilla_carpetas_masivas.zip`.
- Organigrama e instructivo institucional en PDF.
- Referencia BANTER local orientativa con 104 términos para consulta sin conexión.

> La referencia BANTER incluida es una semilla local de apoyo; no es un espejo completo del portal oficial y no reemplaza la TRD/CCD aprobada.

## Módulos

### 1. Administración TRD/CCD

Módulo protegido para:

- cargar nuevas TRD o CCD;
- analizar y previsualizar la información detectada;
- activar versiones;
- eliminar versiones sin uso o archivarlas cuando deban conservar trazabilidad;
- descargar el catálogo normalizado, las fuentes y la plantilla de carpetas.

Contraseña predeterminada: `archivo123`.

En producción se recomienda definir `ADMIN_PASSWORD` como variable de entorno o secreto de Streamlit.

### 2. TRD e instrumentos

- Selección tabla por tabla según la dependencia productora.
- Visualización del Excel original que alimentó el catálogo activo.
- Selector de hojas cuando el libro contiene varias pestañas.
- Descarga del Excel original y de una copia normalizada.
- Consulta del Cuadro de Clasificación Documental para todas las áreas o una dependencia específica.
- Descarga del CCD filtrado y del archivo fuente original.
- Organigrama institucional renderizado en alta resolución y disponible en PDF.
- Las nuevas versiones cargadas desde el módulo administrativo conservan sus archivos fuente en `runtime/catalog_sources/`.

### 3. Clasificación y revisión

- El cargador permanece oculto hasta seleccionar `Todas las dependencias` o `Una dependencia específica`.
- Cuando se elige una dependencia, la clasificación se limita exclusivamente a las series y subseries de esa área.
- Carga individual o por ZIP.
- Extracción de texto y perfiles `OCR completo`, `OCR inteligente` o texto digital.
- OCR de todas las páginas hasta el límite configurable, conservando marcadores por página.
- Detección de año documental.
- Clasificación híbrida probabilística por título principal, nombre, contenido, consenso entre páginas, tipología, palabras, caracteres y análisis semántico latente.
- Desambiguación explícita entre términos cercanos del OCR, por ejemplo `préstamo` frente a `prueba`.
- Edición directa desde la tabla de revisión, limitada a la dependencia seleccionada.
- Selección encadenada: dependencia → serie → subserie.
- `OTROS / OTRAS SERIES` y `OTROS / OTRAS SUBSERIES` aparecen primero.
- BANTER permanece como última alternativa para propuestas sin código oficial.
- Botones `Guardar cambios`, `Marcar todos`, `Desmarcar todos` y `Aprobar marcados`.

Cuando la coincidencia oficial no es suficiente, el documento queda temporalmente en:

`OTROS / OTRAS SERIES — sin código TRD`

### IA local gratuita para BANTER

El motor `core/banter.py` funciona completamente en el equipo:

- TF-IDF de palabras y bigramas;
- n-gramas de caracteres para tolerar variaciones ortográficas;
- LSA/SVD para afinidad semántica;
- ponderación de coincidencias de series, subseries, alias y tipos documentales;
- sin API de pago;
- sin envío de documentos a un proveedor externo.

La búsqueda BANTER está disponible en el editor del módulo 3 y en el módulo 6.

### 4. Documentos aprobados

- Filtros por año, dependencia y nombre.
- Vista previa de documentos.
- Consulta de retención y disposición final.
- Descarga de tabla en Excel, PDF, CSV y JSON.
- Registro de la fuente de clasificación: TRD PROINSALUD, BANTER orientativo o asignación manual.

### 5. Carpetas masivas

Dos modos de exportación:

1. Plantilla codificada suministrada por PROINSALUD.
2. Jerarquía por año, dependencia, serie y subserie.

La opción recomendada conserva la estructura:

```text
CARPETAS_MASIVAS_ACTUALIZADAS/
└── CÓDIGO - DEPENDENCIA/
    └── CÓDIGO.SERIE - SERIE/
        └── CÓDIGO COMPLETO - SUBSERIE/
            └── TIPO DOCUMENTAL/
                └── archivo
```

#### Corrección de carpetas duplicadas

La exportación ahora reutiliza exactamente el nombre existente en la plantilla. Cuando la longitud total de una ruta es elevada, el sistema **no recorta el nombre de la carpeta**: ajusta únicamente el nombre del archivo. Esto evita que aparezcan dos carpetas casi iguales, por ejemplo una completa y otra terminada en `...archiv`.

Las rutas también se deduplican con las reglas de comparación de Windows: sin distinguir mayúsculas/minúsculas y eliminando espacios o puntos finales.

#### Series y subseries apoyadas en BANTER

Las clasificaciones BANTER no reciben códigos inventados. Primero se normalizan acentos, mayúsculas, pluralización y prefijos `SERIE SIN CÓDIGO`. Si la denominación ya existe en la TRD de la dependencia, se reutiliza la carpeta codificada. Solo cuando no existe equivalencia se exporta de forma legible:

```text
CARPETAS_MASIVAS_ACTUALIZADAS/
└── DEPENDENCIA/
    └── SERIE SIN CÓDIGO - Nombre de la serie/
        └── SUBSERIE SIN CÓDIGO - Nombre de la subserie/
            └── archivo
```

El ZIP incluye manifiestos CSV/JSON y una tabla PDF con la fuente de clasificación.

### 6. Catálogo y BANTER

- Búsqueda inteligente en las series y subseries de la TRD activa.
- Filtro opcional por dependencia.
- Consulta BANTER separada como fuente orientativa.
- Las TRD, el CCD y el organigrama se concentran en el módulo 2 para evitar acciones duplicadas.


## Interfaz y modo nocturno

- Interruptor `Modo nocturno` disponible en la barra lateral y en la vista completa de revisión.
- Paleta clara y nocturna aplicada a paneles, controles, pestañas, formularios y fondos.
- Navegación con menos elementos visuales y acciones agrupadas por etapa.
- La vista completa de revisión oculta la barra lateral, el encabezado y el flujo de módulos hasta que se pulse `Volver`.
- Las columnas de evidencia, predicción, fuente, año u observaciones pueden ocultarse o mostrarse según la tarea.
- Los botones principales utilizan morado con texto blanco para mantener contraste en modo claro y nocturno.
- En revisión, seleccione primero una dependencia; la lista de series queda limitada a esa área. Al abrir una fila, la subserie se limita estrictamente a la serie seleccionada.

## Inicio rápido en Windows

1. Instale Python 3.11 o superior.
2. Descomprima completamente el ZIP.
3. Abra la carpeta `PROINSALUD_TRD_IA_V9`.
4. Para leer PDF escaneados, ejecute una vez `instalar_ocr_windows.bat` si Tesseract no está instalado.
5. Ejecute `iniciar_windows.bat`.
6. Abra `http://localhost:8501` si el navegador no se abre automáticamente.

El iniciador guarda el entorno de Python en `%LOCALAPPDATA%\PROINSALUD_TRD\venv`. Esto evita el error **WinError 206: el nombre del archivo o la extensión es demasiado largo**, que se producía al crear `.venv` dentro de una ruta duplicada y extensa.

Si la primera instalación se interrumpe, ejecute `reparar_inicio_windows.bat`. La reparación elimina solamente el entorno de Python y no borra los documentos del aplicativo. Consulte también `SOLUCION_ERROR_INICIO.md`.


## Corrección para nombres de archivo largos en Windows

La aplicación conserva el nombre original del documento en la base de datos, pero utiliza internamente un nombre físico más corto y único dentro de `runtime/uploads/`. Esto evita el error:

```text
FileNotFoundError: [Errno 2] No such file or directory
```

que puede aparecer cuando la ruta completa supera el límite clásico de Windows. La carpeta de cargas también se recrea automáticamente si fue eliminada o todavía no existe. No es necesario renombrar manualmente los PDF, Word o Excel antes de cargarlos.

## Linux o macOS

```bash
chmod +x iniciar_linux_mac.sh
./iniciar_linux_mac.sh
```

O manualmente:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## Docker

```bash
docker build -t proinsalud-documental .
docker run --rm -p 8501:8501 -v "$(pwd)/runtime:/app/runtime" proinsalud-documental
```

## Seguridad

Variables opcionales:

- `APP_PASSWORD`: protege toda la aplicación.
- `ADMIN_PASSWORD`: cambia la contraseña del módulo administrativo.
- `CLASIFICADOR_DATA_DIR`: cambia la ubicación de la base y archivos procesados.

Los originales quedan en `runtime/uploads/` y la base en `runtime/clasificador.sqlite3`.

Para producción:

- cifre el disco;
- limite el acceso por perfiles;
- realice copias de seguridad;
- proteja los secretos;
- registre auditoría;
- no publique documentos sensibles en servicios públicos sin autorización.

## Pruebas

```bash
python -m unittest discover -s tests -v
```

El paquete incluye **38 pruebas automatizadas** para catálogo, clasificación, OCR, revisión, búsqueda BANTER, persistencia, exportación PDF y generación de carpetas masivas, incluidas regresiones específicas para rutas largas y carpetas duplicadas.

## Estructura del proyecto

```text
app.py                             interfaz Streamlit
core/catalog.py                    lectura y normalización TRD/CCD
core/ml_engine.py                  clasificación híbrida probabilística local
core/hierarchy.py                  equivalencias TRD/BANTER y deduplicación
core/banter.py                     consulta semántica BANTER local
core/database.py                   SQLite, versiones y revisión
core/text_extract.py               extracción, OCR y año
core/exporter.py                   tablas y ZIP codificado
data/catalogo_proinsalud.json      catálogo inicial
data/banter_agn_referencia.json    referencia orientativa BANTER
data/fuentes_trd_proinsalud.zip    fuentes institucionales
data/plantilla_carpetas_masivas.zip plantilla institucional
tests/                             pruebas automatizadas
```

## Alcance archivístico

La aplicación es una herramienta de apoyo. No debe ordenar eliminación, selección, conservación, transferencias o incorporación oficial de nuevas series sin validación del responsable de gestión documental y sin aplicar la TRD vigente de la entidad.

## Actualización V7 — visibilidad y OTROS

La versión V7 aplica alto contraste a todos los botones, selectores, menús y popovers. Los documentos que no tengan una coincidencia válida en la TRD activa se exportan en la serie temporal `OTROS - OTRAS SERIES SIN CÓDIGO TRD`, dentro de la dependencia detectada o en `OTROS - DEPENDENCIA POR DEFINIR` cuando el área tampoco pueda establecerse.


## Actualización V8
Consulte `MEJORAS_CONTRASTE_DESPLEGABLES_SELECCION_V8.md`.


## Actualización V8 — contraste y selección masiva

- El editor de tabla conserva una paleta clara de alto contraste aun cuando el aplicativo está en modo nocturno.
- Los menús desplegables internos muestran fondo claro y texto azul oscuro.
- Al abrir la revisión se preselecciona una dependencia con documentos visibles, recuperando la edición directa de Serie y Subserie.
- **Marcar todos** activa todas las casillas de aprobación visibles; **Aprobar marcados** confirma el lote.
- Las series se limitan a la dependencia seleccionada y, al filtrar una serie, las subseries se limitan a esa serie.


## Actualización V9 — TRD por tabla y carga organizada

- Nuevo módulo independiente `TRD e instrumentos`.
- Visualización y descarga de cada Excel TRD original.
- CCD filtrable y descargable por área.
- Organigrama en alta resolución.
- Persistencia de archivos fuente por versión de catálogo.
- La carga documental solo aparece después de definir su alcance institucional.
