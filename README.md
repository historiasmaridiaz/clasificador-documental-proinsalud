# Clasificador documental TRD/CCD — PROINSALUD

Aplicación web local en Python para cargar Tablas de Retención Documental (TRD), Cuadros de Clasificación Documental (CCD) y documentos por clasificar. Extrae contenido y OCR, detecta el año, propone códigos archivísticos mediante recuperación de información con *machine learning*, permite revisión humana y exporta una tabla o un ZIP organizado según el instructivo IAGED-10.

El proyecto viene preconfigurado con un catálogo normalizado a partir de `TRD PROINSALUD.rar`.

La interfaz usa la identidad visual institucional azul y naranja de PROINSALUD e incluye un módulo de instrucciones de manejo.

## Funciones principales

- Carga de TRD/CCD en `.xlsx`, `.xlsm`, `.xls`, `.csv`, `.tsv`, `.zip` y `.rar`.
- Consulta interactiva de la TRD por área, con búsqueda, retención, disposición final y procedimiento.
- Cuadro de Clasificación Documental filtrable por dependencia y texto.
- Vista previa y descarga del organigrama institucional incluido, con acceso al organigrama publicado por PROINSALUD.
- Módulo interactivo de instrucciones de manejo y vista previa del instructivo IAGED-10 incluido.
- Detección de dependencia, serie, subserie, tipos documentales, retención, disposición final y procedimiento.
- Extracción de texto desde PDF, Word, Excel, PowerPoint, ODT, correo EML, texto, HTML, XML, JSON, imágenes y archivos ZIP.
- OCR real de páginas PDF escaneadas e imágenes mediante Tesseract y PyMuPDF.
- Detección del año documental desde el nombre, encabezado OCR, contenido y metadatos.
- Prioridad para fecha interna de creación/ZIP y, cuando no existe, la fecha completa más reciente detectada por OCR.
- Selección de dependencia antes de cargar para limitar y mejorar la clasificación.
- Botones para continuar cargando lotes al mismo listado o limpiar la selección y comenzar nuevamente.
- Clasificador local y explicable: combina TF‑IDF de palabras y caracteres con similitud coseno.
- Filtro opcional por dependencia.
- Lista de alternativas con puntaje de similitud y nivel de confianza.
- Revisión humana con estados `Pendiente`, `Aprobada`, `Corregida` y `Descartada`.
- Módulo de asignación manual: filtra por dependencia, busca por nombre y muestra sección, subsección, serie y subserie.
- Aprendizaje incremental: los documentos aprobados o corregidos refuerzan el código correspondiente en búsquedas posteriores.
- Persistencia en SQLite.
- Tabla previa y vista previa del documento antes de exportar.
- Vista previa de PDF renderizada internamente, sin depender del componente opcional `st.pdf`.
- Exportación de la tabla a Excel, CSV, JSON y PDF imprimible.
- ZIP organizado por año/dependencia/serie/subserie, con opción de incluir la estructura TRD vacía completa.

## Inicio rápido en Windows

1. Instale [Python 3.11 o superior](https://www.python.org/downloads/).
2. Descomprima el proyecto.
3. Haga doble clic en `iniciar_windows.bat`.
4. El navegador abrirá `http://localhost:8501`.

En PowerShell también puede ejecutar:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

## Inicio en Linux o macOS

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
docker build -t clasificador-trd .
docker run --rm -p 8501:8501 -v "$(pwd)/runtime:/app/runtime" clasificador-trd
```

## Publicar como aplicación web

El proyecto está preparado para GitHub y Streamlit Community Cloud:

- `requirements.txt`: dependencias Python;
- `packages.txt`: Tesseract OCR y paquete de idioma español;
- `.github/workflows/tests.yml`: pruebas automáticas en cada actualización;
- `DEPLOY_WEB.md`: instrucciones completas para GitHub y publicación web;
- `GUIA_GITHUB.html`: guía visual que puede abrir con doble clic en Windows;
- `SECURITY.md`: precauciones para documentos institucionales.

Consulte [DEPLOY_WEB.md](DEPLOY_WEB.md). Puede configurar `APP_PASSWORD` en los secretos de Streamlit para activar la pantalla básica de acceso sin publicar la contraseña en GitHub.

Esta aplicación no funciona subiendo únicamente un archivo HTML: OCR, SQLite, clasificación TF-IDF y creación de ZIP necesitan el servidor Python. En GitHub debe cargar todos los archivos del proyecto y desplegar `app.py` con Streamlit.

La aplicación evita claves visuales duplicadas aunque se cargue varias veces el mismo documento.

## Flujo de uso

1. Abra **Fuentes TRD/CCD** para consultar la TRD por área, el CCD, el organigrama o cargar una nueva versión.
2. Abra **Instrucciones de manejo** para recorrer el proceso y consultar el instructivo institucional.
3. Abra **Clasificar archivos**, seleccione la dependencia y configure OCR y detección de año.
4. Cargue documentos individuales o un ZIP y revise el año, las alternativas y el contenido extraído.
5. Si necesita decidir directamente, use **Asignación manual**, filtre el área, escriba el nombre y seleccione serie/subserie.
6. Abra **Revisión humana** para confirmar o corregir tanto el año como el código, y descargar la tabla en PDF o Excel.
7. Abra **Exportar**, filtre año/dependencia, revise la tabla y la vista previa, pulse **Preparar archivo comprimido** y luego **Descargar ZIP**.

## Estructura del ZIP según IAGED-10

```text
2025/
└── 3002.2 - GESTION DOCUMENTAL/
    └── 3002.2.28 - INFORMES/
        └── 3002.2.28.63 - Informes de Gestión/
            └── documento.pdf
```

Cuando una serie no tiene subserie, el documento se ubica directamente dentro de la carpeta de serie. La opción **Incluir estructura TRD completa** agrega también las carpetas vacías correspondientes a las dependencias y años seleccionados.

## Cómo funciona el modelo

El sistema no usa una API externa ni un modelo generativo. Para cada código crea un documento de entrenamiento con:

- código y dependencia;
- nombre de la serie y subserie;
- tipos documentales;
- procedimiento de retención;
- ejemplos previamente aprobados o corregidos.

Calcula dos espacios TF‑IDF: palabras y bigramas, más n‑gramas de caracteres. La puntuación final combina ambas similitudes y aplica un refuerzo cuando el nombre o el contenido contiene un código archivístico exacto. El resultado es un **puntaje de similitud**, no una probabilidad ni una decisión jurídica.

## Datos y privacidad

- La aplicación trabaja localmente.
- La base está en `runtime/clasificador.sqlite3`.
- Los originales cargados quedan en `runtime/uploads/`.
- Para borrar el historial de una instalación de pruebas, cierre la aplicación y elimine la carpeta `runtime/`.
- En producción, cifre el disco, proteja el acceso, defina roles, registre auditoría y haga copias de seguridad.

## OCR

El programa detecta páginas PDF con poco o ningún texto, las convierte temporalmente a imagen con PyMuPDF y ejecuta OCR. El paquete Python `pytesseract` es el conector, pero también debe instalar el programa Tesseract y el idioma español:

- Windows: instale Tesseract y agréguelo al `PATH`.
- Ubuntu/Debian: `sudo apt install tesseract-ocr tesseract-ocr-spa`.
- macOS: `brew install tesseract tesseract-lang`.

Si el paquete de idioma español no está disponible, el sistema intenta el idioma predeterminado de Tesseract y muestra una advertencia. Puede limitar el número máximo de páginas OCR desde la interfaz.

## RAR

La lectura de RAR desde la interfaz usa `rarfile` y necesita 7‑Zip, UnRAR o una herramienta compatible instalada. Si no está disponible, descomprima el RAR y cargue los Excel, o conviértalo a ZIP. El catálogo PROINSALUD incluido ya fue procesado y no requiere abrir el RAR.

## Regenerar el catálogo inicial

```bash
python scripts/build_catalog.py "/ruta/a/TRD PROINSALUD.rar" \
  --output data/catalogo_proinsalud.json \
  --name "PROINSALUD"
```

También puede apuntar a un directorio con múltiples Excel.

## Pruebas

```bash
python -m unittest discover -s tests
```

## Estructura

```text
app.py                    interfaz Streamlit
core/catalog.py           lectura y normalización TRD/CCD
core/text_extract.py      extracción de documentos
core/ml_engine.py         índice y clasificación TF-IDF
core/database.py          persistencia SQLite y aprendizaje
core/exporter.py          manifiestos y ZIP clasificado
data/                     catálogo, organigrama e instructivo institucional
scripts/build_catalog.py  regeneración del catálogo
tests/                    pruebas automatizadas
```

## Criterio archivístico

La herramienta asiste la búsqueda y organización. No debe ordenar transferencias, eliminación, selección o conservación sin validación del responsable de gestión documental y sin aplicar la TRD vigente y aprobada de la entidad.
