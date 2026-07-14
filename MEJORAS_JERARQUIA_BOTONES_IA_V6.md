# Mejoras de jerarquía, botones e inteligencia artificial — V6

## Botones y contraste

Los botones principales usan una paleta morada con texto blanco y estados de interacción visibles. Los botones secundarios conservan el color del panel y un borde definido. La regla funciona en modo claro y nocturno.

## Revisión por dependencia

En la tabla de revisión, la opción `Dependencia de trabajo` controla las series disponibles:

1. Al seleccionar `GESTIÓN DOCUMENTAL`, solo aparecen las series oficiales de Gestión Documental.
2. `OTROS / OTRAS SERIES — sin código TRD` aparece siempre en primer lugar.
3. Cuando se selecciona una serie en el editor del documento, solo aparecen las subseries pertenecientes a esa serie.
4. Con `Todas (solo consulta)`, la jerarquía queda bloqueada en la tabla para evitar cruces entre dependencias; la fila puede abrirse en el editor jerárquico.

## Flujo OTROS

Al seleccionar OTROS se muestran dos acciones claras:

- `Agregar serie`: permite escribir una serie y una subserie manuales.
- `Buscar serie en BANTER`: consulta la referencia terminológica y permite seleccionar un resultado.

En ambos flujos existe `Volver a la TRD`. Antes de guardar, el sistema compara la denominación con la TRD activa. Si ya existe, reutiliza el código oficial y evita crear una carpeta duplicada sin código.

## Modelo PROINSALUD-HYBRID-5

El título, el nombre del archivo y las primeras líneas tienen mayor peso que menciones secundarias del cuerpo. También se añadieron reglas de intención para diferenciar palabras cercanas que el OCR o los n-gramas pueden confundir.

Caso de regresión incorporado:

- Título: `PRÉSTAMO DE HISTORIAS CLÍNICAS`.
- Resultado esperado: `3002.2.30.246 - Instrumentos de Control de Registro de Prestamo de Historias Clínicas`.
- Una mención secundaria a pruebas clínicas no puede desplazar la clasificación hacia una serie de resultados de pruebas.

## Pruebas

La versión incluye 38 pruebas automatizadas, incluyendo selección jerárquica por dependencia/serie y la desambiguación préstamo/pruebas.
