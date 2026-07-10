# Publicar el clasificador como aplicación web

La opción más directa es GitHub + Streamlit Community Cloud. El repositorio ya incluye `requirements.txt`, `packages.txt`, configuración de Streamlit y pruebas de GitHub Actions.

## Importante: no es una página HTML estática

No cargue solamente un archivo HTML en GitHub Pages. El clasificador utiliza Python para OCR, lectura de TRD/CCD, SQLite, generación de PDF/Excel y creación de ZIP. Debe subir **todo el contenido del proyecto** y ejecutarlo con Streamlit Community Cloud, Docker o un servidor Python.

## 1. Crear el repositorio en GitHub

1. Ingrese a <https://github.com/new>.
2. Cree un repositorio, por ejemplo `clasificador-documental-proinsalud`.
3. Elija **Private** si procesará información institucional o documentos con datos personales.
4. Descomprima el ZIP y abra la carpeta `clasificador_documental_proinsalud`.
5. Cargue **el contenido interno de esa carpeta** en la raíz del repositorio. `app.py` debe quedar visible en la página principal.

También puede usar Git Bash dentro de la carpeta:

```bash
git init
git add .
git commit -m "Versión inicial del clasificador documental"
git branch -M main
git remote add origin https://github.com/SU_USUARIO/clasificador-documental-proinsalud.git
git push -u origin main
```

Guía oficial: <https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github>

## 2. Desplegar en Streamlit Community Cloud

1. Ingrese a <https://share.streamlit.io/> con su cuenta de GitHub.
2. Pulse **Create app**.
3. Seleccione el repositorio y la rama `main`.
4. En **Main file path**, escriba `app.py`.
5. En configuración avanzada seleccione Python 3.12.
6. Pulse **Deploy**.

Streamlit instalará las dependencias Python desde `requirements.txt` y Tesseract OCR desde `packages.txt`.

Guías oficiales:

- <https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app>
- <https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies>

## 3. Proteger la aplicación con contraseña

En la configuración avanzada de Streamlit, abra **Secrets** y agregue:

```toml
APP_PASSWORD = "CAMBIE_ESTA_CONTRASENA"
```

No guarde la contraseña en GitHub. Si no configura `APP_PASSWORD`, la aplicación quedará accesible sin esta pantalla de protección.

## 4. Advertencia sobre persistencia

Streamlit Community Cloud puede reiniciar o reconstruir el contenedor. La base SQLite y los archivos almacenados localmente pueden perderse durante esos eventos. Descargue los ZIP y manifiestos después de cada sesión.

Para uso institucional permanente se recomienda desplegar el Docker incluido en un servidor controlado y montar `runtime/` en un volumen persistente, además de implementar autenticación corporativa, cifrado, copias de seguridad y control de acceso.
