# Solución aplicada al error de inicio de Windows

## Error identificado

En el video se observa el mensaje:

```text
ERROR: Could not install packages due to an OSError: [WinError 206]
El nombre del archivo o la extensión es demasiado largo
```

El fallo ocurría porque el entorno virtual `.venv` se creaba dentro de una ruta duplicada y muy extensa, por ejemplo:

```text
...\clasificador_documental_PROINSALUD_actualizado\
   clasificador_documental_PROINSALUD_actualizado\.venv\...
```

Al instalar Streamlit, Windows alcanzaba el límite de longitud de ruta y cancelaba el proceso antes de abrir el aplicativo.

## Corrección incluida

`iniciar_windows.bat` ahora:

- crea el entorno virtual en `%LOCALAPPDATA%\PROINSALUD_TRD\venv`;
- no utiliza la carpeta local `.venv` del proyecto;
- ejecuta Streamlit mediante el Python exacto del entorno;
- verifica las dependencias antes de abrir la aplicación;
- conserva la ventana abierta cuando ocurre un error;
- evita reinstalar todo en cada arranque cuando el entorno ya está correcto.

El paquete también usa una carpeta raíz corta: `PROINSALUD_TRD`.

## Cómo iniciar

1. Extraiga el ZIP completamente.
2. Abra la carpeta `PROINSALUD_TRD`.
3. Ejecute `iniciar_windows.bat`.
4. Espere a que termine la instalación inicial.
5. Abra `http://localhost:8501` si el navegador no se abre automáticamente.

## Reparación automática

Si una instalación se interrumpe o queda incompleta, ejecute:

```text
reparar_inicio_windows.bat
```

Este archivo reconstruye únicamente el entorno de Python. No elimina documentos del aplicativo.
