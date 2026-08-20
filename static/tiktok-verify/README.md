# Verificación de dominio TikTok (método archivo .txt)

TikTok pide un archivo en la **raíz** del dominio que verifica ngrok:

`https://TU.ngrok-free.dev/tiktokXXXX.txt`

Ese host apunta a FastAPI `:8000`, no a Vite `:5173`.

## Opción rápida (recomendado)

1. En TikTok Developers → Verify URL properties → método archivo `.txt`.
2. Copia el **nombre** (ej. `tiktokABC123.txt`) y el **contenido** (a menudo igual sin extensión).
3. En `.env`:

```env
TIKTOK_VERIFY_FILENAME=tiktokABC123.txt
TIKTOK_VERIFY_CONTENT=tiktokABC123
```

4. Reinicia uvicorn (y deja ngrok a `:8000`).
5. Abre `https://TU.ngrok-free.dev/tiktokABC123.txt` — debe verse solo el texto.
6. Pulsa Verify en TikTok.

## Opción archivo en disco

Deja aquí el `.txt` **con el nombre exacto** que da TikTok (ej. `tiktokABC123.txt`).
El cuerpo del archivo debe ser el texto exacto del portal (una línea, sin HTML).

FastAPI lo servirá en `/{nombre-del-archivo}`.
