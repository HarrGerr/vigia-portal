# -*- coding: utf-8 -*-
# VIGÍA EXTERNO DEL PORTAL (01/11/2026, Gerard: «un vigía externo que avise si el portal se cae»).
# Corre en GitHub Actions cada 5 minutos, FUERA de la PC: si la PC se apaga, se queda sin internet o el túnel se cae, el
# vigía de la PC (herramientas/vigia_portal.py del portal) no puede avisar; este sí.
#   · pregunta a /api/salud del portal (ok, versión y si las dos bases contestan) hasta 3 veces en ~1 minuto: un reinicio
#     del portal al publicar dura segundos y no debe avisar;
#   · si sigue mal, la corrida FALLA a propósito y GitHub avisa al dueño del repositorio (correo y app de GitHub). Falla
#     una vez al caer y otra cada 2 horas mientras siga caído; las demás corridas salen bien para no llenar de avisos;
#   · SIN claves ni datos personales (Gerard: el repositorio es público; nada de WhatsApp aquí);
#   · el estado entre corridas va en estado/estado.json (lo guarda el caché de Actions, ver .github/workflows/vigia.yml).
# PRUEBA=1 hace fallar la corrida para probar que el aviso de GitHub llega.
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

LIMA = timezone(timedelta(hours=-5))
VIGILADOS = [("portal", "El portal (portal.desarrollozip.com)", "https://portal.desarrollozip.com/api/salud")]
ESTADO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "estado", "estado.json")
INTENTOS, PAUSA_S = 3, 25
REPETIR_CADA = timedelta(hours=2)
BASES = {"owner": "la base del portal", "inventario": "la base de la app (inventario-app)"}


def ahora():
    return datetime.now(LIMA)


def duracion(desde):
    minutos = int((ahora() - datetime.fromisoformat(desde)).total_seconds() // 60)
    return f"{minutos} min" if minutos < 120 else f"{minutos // 60} h {minutos % 60} min"


def revisar(url):
    """None si responde bien; si no, el motivo en pocas palabras."""
    motivo = None
    for intento in range(INTENTOS):
        if intento:
            time.sleep(PAUSA_S)
        try:
            pedido = urllib.request.Request(url, headers={"User-Agent": "vigia-externo-desarrollozip"})
            with urllib.request.urlopen(pedido, timeout=20) as r:
                cuerpo = json.loads(r.read() or b"{}")
            if cuerpo.get("ok"):
                return None
            caidas = [BASES.get(k, k) for k, v in (cuerpo.get("bases") or {}).items() if v is False]
            motivo = "no contesta " + " ni ".join(caidas) if caidas else "responde, pero dice que no está bien"
        except urllib.error.HTTPError as e:
            # 502/530 de Cloudflare = el túnel no llega a la PC (apagada, sin internet o el servidor del portal caído)
            motivo = f"error {e.code}" + (" (Cloudflare no llega a la PC)" if e.code in (502, 503, 504, 530) else "")
        except Exception as e:
            motivo = f"no responde ({type(e).__name__})"
    return motivo


def main():
    try:
        with open(ESTADO, encoding="utf-8") as f:
            estado = json.load(f)
    except (OSError, ValueError):
        estado = {}
    avisos = []
    if os.environ.get("PRUEBA") == "1":
        avisos.append("PRUEBA: el vigía externo está activo y revisa el portal cada 5 minutos.")
    for clave, nombre, url in VIGILADOS:
        e = estado.get(clave) or {}
        motivo = revisar(url)
        if motivo is None:
            print(f"{nombre}: bien")
            if e.get("caido_desde"):
                print(f"Volvió a responder a las {ahora():%H:%M}. Estuvo caído {duracion(e['caido_desde'])}.")
            estado[clave] = {}
            continue
        if not e.get("caido_desde"):
            e = {"caido_desde": ahora().isoformat()}
        ultimo = e.get("ultimo_aviso")
        desde = datetime.fromisoformat(e["caido_desde"]).strftime("%d/%m %H:%M")
        print(f"{nombre}: MAL desde las {desde} ({motivo})")
        if not ultimo or ahora() - datetime.fromisoformat(ultimo) >= REPETIR_CADA:
            avisos.append(f"{nombre} no responde desde las {desde} (hora de Lima): {motivo}. Puede ser la PC apagada o "
                          "reiniciándose, sin internet, o el túnel o el servidor del portal caídos.")
            e["ultimo_aviso"] = ahora().isoformat()
        estado[clave] = e
    os.makedirs(os.path.dirname(ESTADO), exist_ok=True)
    with open(ESTADO, "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False)
    for a in avisos:
        # «::error::» lo muestra GitHub en el resumen de la corrida y en el aviso
        print(f"::error title=Portal caído::{a}")
    sys.exit(1 if avisos else 0)


if __name__ == "__main__":
    main()
