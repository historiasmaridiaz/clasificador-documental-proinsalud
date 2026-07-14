# Actualización V6 — jerarquía y desambiguación

- Botones principales morados con texto blanco y contraste en modo claro/nocturno.
- Series limitadas a la dependencia seleccionada.
- Subseries limitadas a la serie seleccionada en el editor jerárquico.
- `OTROS` aparece primero y ofrece `Agregar serie` o `Buscar serie en BANTER`.
- BANTER dejó de asignarse automáticamente en casos débiles; se consulta voluntariamente como última alternativa.
- Modelo `PROINSALUD-HYBRID-5` con mayor peso para título y desambiguación `préstamo`/`prueba`.
- Regresión validada para `Préstamo de historias clínicas` → código `3002.2.30.246`.
- 38 pruebas automatizadas aprobadas.


## Actualización de interfaz V5

- Modo nocturno con interruptor persistente durante la sesión.
- Vista completa de la tabla de revisión, ocultando navegación, encabezado y flujo de módulos.
- Selector de columnas visibles sin perder valores de las columnas ocultas al guardar.
- Columnas predeterminadas centradas en archivo, código, dependencia, serie y subserie.
- `OTROS / OTRAS SERIES` y `OTROS / OTRAS SUBSERIES` aparecen al inicio de los desplegables.
- Los desplegables directos contienen únicamente opciones de la TRD activa; BANTER quedó separado como última opción.
- Acciones simplificadas: `Guardar cambios`, `Marcar todos`, `Desmarcar todos` y `Aprobar marcados`.
- Pruebas nuevas para el orden de opciones y la conservación de columnas ocultas.

# Cambios realizados

## Interfaz y revisión

- Navegación organizada en cinco módulos operativos.
- Panel inicial con flujo visual y métricas.
- Terminología clara para afinidad, clasificación final y estado.
- Tabla de revisión editable con columnas de dependencia, serie y subserie.
- Nueva casilla `Abrir` para seleccionar una fila y mostrar el editor jerárquico por documento.
- Listas encadenadas: dependencia → serie → subserie.
- Aprobación desde la tabla o desde el editor ampliado.

## Administración

- Acceso privado con contraseña predeterminada `archivo123`.
- Carga y activación de nuevas TRD/CCD.
- Eliminación segura de versiones no usadas.
- Archivado de versiones con trazabilidad histórica.
- Descarga de catálogo, fuentes y plantilla.

## Clasificación y BANTER

- Selección entre todas las áreas o una dependencia.
- Nuevo modelo híbrido probabilístico con título principal, nombre de archivo, contenido, consenso por páginas, tipología documental, TF-IDF, n-gramas y LSA/SVD.
- Probabilidad normalizada, relevancia, margen, evidencia y revisión obligatoria cuando la señal es débil.
- Categoría temporal OTROS / OTRAS SERIES sin código oficial.
- Integración de una referencia BANTER local orientativa con 104 términos.
- Motor gratuito local con TF-IDF, n-gramas de caracteres y LSA/SVD.
- Consulta BANTER integrada en los módulos 2 y 5.
- Las denominaciones BANTER se comparan con la TRD activa: si ya existen, reutilizan el código y la carpeta oficial; si no existen, permanecen sin código.
- Registro de la fuente de clasificación en los manifiestos.


## OCR y comprensión documental

- Perfil `OCR completo` seleccionado de manera predeterminada.
- OCR por página con Tesseract local, lectura de encabezados y combinación con la capa digital del PDF.
- Detección automática del motor en rutas comunes de Windows.
- Nuevo archivo `instalar_ocr_windows.bat` para instalar o verificar Tesseract.
- El título y la tipología dominante tienen mayor peso que una mención aislada en páginas posteriores.
- Equivalencia contextual de `comité de archivo clínico` con `Comité de Historias Clínicas`.

## Corrección de carpetas masivas

- Identificada la causa del duplicado mostrado en la captura: la plantilla incluía la carpeta completa, pero el ajuste de longitud recortaba también el nombre de la carpeta al guardar el documento, generando una segunda ruta casi idéntica.
- Los nombres de carpetas provenientes de la plantilla ahora se conservan exactamente.
- Cuando la ruta es extensa se recorta únicamente el nombre del archivo.
- Deduplicación con semántica de Windows: comparación sin mayúsculas/minúsculas y sin espacios o puntos finales.
- Reutilización exacta de la subcarpeta de tipo documental existente.
- Las series/subseries BANTER solo crean `SERIE SIN CÓDIGO` y `SUBSERIE SIN CÓDIGO` cuando no existe equivalencia oficial en la misma dependencia.
- Manifiesto CSV, JSON y tabla PDF incluidos dentro del ZIP.

## Datos

- Catálogo regenerado desde los archivos adjuntos.
- Corrección automática de un segmento repetido en seis códigos fuente de SIAU.
- Resultado final: 562 clasificaciones, 40 dependencias, 194 series y 529 subseries.

## Calidad

- 36 pruebas automatizadas superadas.
- Pruebas de regresión para rutas largas, carpetas duplicadas, equivalencia BANTER/TRD y el caso de acta de comité clínico con una mención secundaria a TRD.
- Validación adicional con la plantilla institucional real y la ruta `3002.2.30.293`.
- Compilación de todos los módulos Python validada.
- Inicio de Streamlit y endpoint de salud verificados.

## Corrección de inicio en Windows

- Identificado en video el error `WinError 206`: ruta o nombre de archivo demasiado largo durante la instalación de Streamlit.
- El entorno virtual se instala en `%LOCALAPPDATA%\PROINSALUD_TRD\venv`.
- El iniciador verifica Python, dependencias y archivos antes de ejecutar la aplicación.
- La consola permanece abierta cuando ocurre un error.
- `reparar_inicio_windows.bat` reconstruye instalaciones incompletas sin borrar documentos.

## Corrección de carga de archivos en Windows

- Corregido `FileNotFoundError: [Errno 2] No such file or directory` al guardar documentos con nombres extensos.
- El nombre físico almacenado se recorta de forma segura, conservando la extensión y un prefijo hash único.
- El nombre original completo continúa registrado en la base de datos y visible en la interfaz.
- La carpeta `runtime/uploads` se recrea automáticamente antes de cada escritura.
- Se añadió una ruta de respaldo basada únicamente en hash si Windows rechaza la primera ruta.
- La corrección aplica tanto a la carga por lote como a la asignación manual.
- Se agregaron dos pruebas de regresión específicas para nombres largos y carpetas de carga inexistentes.

## Versión 2026.07.13-VISIBILITY-OTHER-7

- Tema visual centralizado y controles de alto contraste en todo el aplicativo.
- Corrección de botones blancos, incluido `Columnas`, descargas, enlaces y botones secundarios.
- Selectores activos y deshabilitados visibles en modo nocturno.
- Menús desplegables y popovers adaptados al modo claro/nocturno.
- Documentos sin coincidencia válida enviados a una carpeta única `OTROS - OTRAS SERIES SIN CÓDIGO TRD`.
- Creación explícita de la jerarquía de carpetas dentro del ZIP.
- Eliminación de la salida paralela `SIN_CLASIFICACION` para documentos no identificados.


## Actualización V8
Consulte `MEJORAS_CONTRASTE_DESPLEGABLES_SELECCION_V8.md`.


## Versión 2026.07.13-TRD-INSTRUMENTS-SCOPE-9

- Nuevo módulo 2 para TRD, CCD y organigrama.
- Vista y descarga de los Excel originales del catálogo activo.
- Persistencia de fuentes por versión en `runtime/catalog_sources`.
- La carga del módulo 3 se habilita solo después de elegir todas las dependencias o una dependencia específica.
- El módulo 6 queda concentrado en la búsqueda TRD y BANTER para evitar duplicidad de acciones.
