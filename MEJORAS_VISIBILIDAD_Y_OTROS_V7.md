# PROINSALUD TRD IA V7 — visibilidad y documentos fuera de TRD

## Controles de alto contraste

Se centralizó el tema visual en `core/ui_theme.py`. El nuevo estilo cubre:

- botones primarios, secundarios, descargas y enlaces;
- el botón de popover `Columnas`;
- selectores y multiselectores activos o deshabilitados;
- menús desplegables, opciones y popovers abiertos;
- botones de carga de archivos, expansores y controles en modo nocturno;
- títulos y encabezados, evitando texto oscuro sobre fondos oscuros.

Los botones de acción usan morado y los controles secundarios/selectores usan azul índigo oscuro, siempre con texto blanco.

## Documentos sin coincidencia en la TRD

Todo documento sin código válido en el catálogo activo se convierte explícitamente en una clasificación temporal `OTROS / OTRAS SERIES — sin código TRD`.

En la exportación masiva se crea una única ruta:

```text
CARPETAS_MASIVAS_ACTUALIZADAS/
└── [DEPENDENCIA o OTROS - DEPENDENCIA POR DEFINIR]/
    └── OTROS - OTRAS SERIES SIN CÓDIGO TRD/
        └── documento.ext
```

Si el modelo alcanzó a reconocer la dependencia, la carpeta `OTROS` se crea dentro de esa dependencia. Si tampoco se identifica el área, se utiliza `OTROS - DEPENDENCIA POR DEFINIR`.

No se inventan códigos oficiales. Las series manuales o BANTER con nombre definido continúan como `SERIE SIN CÓDIGO - ...`, salvo que exista equivalencia en la TRD activa, caso en el cual se reutiliza la carpeta codificada oficial.

## Validaciones

Se agregaron pruebas para:

- controles de alto contraste en modo claro y nocturno;
- vista completa sin navegación;
- documento completamente sin clasificación;
- documento con dependencia probable pero serie fuera de la TRD;
- creación explícita de la carpeta `OTROS` en el ZIP;
- ausencia de rutas `SIN_CLASIFICACION` para documentos no identificados.
