# Corrección del error al guardar documentos

## Error identificado

En Windows podía aparecer:

```text
FileNotFoundError: [Errno 2] No such file or directory
```

El problema se producía cuando la suma de la ruta del proyecto y el nombre muy largo del documento superaba el límite de ruta admitido por algunas configuraciones de Windows. El directorio podía existir y aun así Python informar que el archivo no se encontraba.

## Solución aplicada

- Se conserva el nombre original completo en la base de datos.
- El archivo físico recibe un nombre corto con hash único.
- Se preserva la extensión original, por ejemplo `.pdf`.
- `runtime/uploads` se recrea antes de guardar cada documento.
- Si Windows rechaza la primera ruta, se usa automáticamente un nombre mínimo basado en hash.

## Qué debe hacer el usuario

1. Cerrar la aplicación anterior.
2. Extraer esta versión corregida en una carpeta nueva.
3. Ejecutar `iniciar_windows.bat`.
4. Volver a cargar el documento que produjo el error.

No es necesario acortar el nombre del documento manualmente.
