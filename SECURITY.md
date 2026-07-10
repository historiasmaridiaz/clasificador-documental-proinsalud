# Seguridad y tratamiento de documentos

- No publique historias clínicas, documentos laborales ni información personal en una aplicación web pública.
- Use un repositorio privado y configure `APP_PASSWORD` como mínimo.
- La contraseña opcional de esta versión es una barrera básica, no reemplaza autenticación corporativa ni perfiles de usuario.
- Para producción, use HTTPS, cifrado de disco, almacenamiento persistente, copias de seguridad, registros de auditoría y acceso por roles.
- Los archivos cargados se guardan temporalmente en `runtime/uploads/` mientras exista la instalación.
- No suba `runtime/`, `.env` ni `.streamlit/secrets.toml` al repositorio. Ya están incluidos en `.gitignore`.

