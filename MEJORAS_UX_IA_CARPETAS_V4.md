# Versión UX–IA 4

## Objetivo

Simplificar la experiencia de uso, mejorar la lectura de documentos y evitar que una denominación BANTER duplique una serie ya codificada en la TRD.

## Interfaz

- Navegación con nombres simples y sin exceso de iconos.
- Inicio con acceso directo a cada módulo.
- Flujo visible: administrar, clasificar, aprobar, exportar y consultar.
- Tabla de revisión editable con casillas `Abrir` y `Aprobar`.
- Editor por documento con listas encadenadas de dependencia, serie y subserie.
- Aprobación individual, de marcados o de todos los visibles.

## OCR y clasificación

- OCR completo por página como opción predeterminada.
- OCR inteligente para procesar encabezados y páginas sin texto digital.
- Índice híbrido local: palabras, caracteres, LSA, título, cuerpo, páginas y aprendizaje por correcciones.
- El encabezado y la tipología documental dominan sobre menciones incidentales.
- Caso de regresión incluido: un acta de comité de archivo clínico no se clasifica como Tabla de Retención Documental por una mención secundaria.

## Carpetas

- Las propuestas BANTER/manuales se normalizan antes de exportar.
- Si la serie ya existe en la TRD de la dependencia, se usa la carpeta codificada.
- Ejemplo corregido: `INSTRUMENTOS ARCHIVÍSTICOS` reutiliza `3002.2.29 - INSTRUMENTOS ARCHIVÍSTICOS`.
- Las carpetas sin código solo se crean cuando no existe equivalencia oficial.
- Las rutas largas conservan los nombres de carpeta; solo se reduce el nombre físico del archivo.

## Validación

Ejecutar:

```bash
python -m unittest discover -s tests -v
python -m compileall -q .
```
