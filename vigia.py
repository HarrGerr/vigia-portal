# -*- coding: utf-8 -*-
# VIGÍA EXTERNO DEL PORTAL (01/11/2026, Gerard: «un vigía externo que avise si el portal se cae, que me llegue al WhatsApp»).
# Corre en GitHub Actions cada 5 minutos, FUERA de la PC: si la PC se apaga, se queda sin internet o el túnel se cae, el
# vigía de la PC (herramientas/vigia_portal.py del portal) no puede avisar; este sí.
#   · pregunta a /api/salud del portal (ok, versión y si las dos bases contestan) hasta 3 veces en ~1 minuto: un reinicio
#     del portal al publicar dura segundos y no debe avisar;
#   · si sigue mal, manda UN WhatsApp (CallMeBot, el mismo número de los avisos) y lo repite cada 2 horas mientras siga
#     caído; cuando vuelve, avisa cuánto duró;
#   · el estado entre corridas va en estado/estado.json (lo guarda el caché de Actions, ver .github/workflows/vigia.yml).
# Variables: CALLMEBOT_TELEFONO y CALLMEBOT_CLAVE (secretos del repositorio). PRUEBA=1 manda un WhatsApp de prueba.
# SIN_WHATSAPP=1 solo imprime lo que mandaría.
import json
import os
import time
import urllib.error
import urllib.parse
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


def hora(iso):
    return datetime.fromisoformat(iso).astimezone(LIMA).strftime("%d/%m %H:%M")


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


def whatsapp(texto):
    tel, clave = os.environ.get("CALLMEBOT_TELEFONO", ""), os.environ.get("CALLMEBOT_CLAVE", "")
    if os.environ.get("SIN_WHATSAPP") == "1":
        print("WhatsApp (no enviado):\n" + texto)
        return True
    if not tel or not clave:
        print("Faltan los secretos CALLMEBOT_TELEFONO / CALLMEBOT_CLAVE")
        return False
    url = ("https://api.callmebot.com/whatsapp.php?phone=" + urllib.parse.quote(tel) + "&text="
           + urllib.parse.quote(texto) + "&apikey=" + urllib.parse.quote(clave))
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            respuesta = r.read().decode("utf-8", "replace").lower()
        ok = not any(p in respuesta for p in ("error", "invalid", "blocked", "not allowed"))
    except Exception as e:
        print(f"WhatsApp no salió: {type(e).__name__}")
        return False
    print("WhatsApp enviado" if ok else "WhatsApp rechazado por CallMeBot")
    return ok


def main():
    try:
        with open(ESTADO, encoding="utf-8") as f:
            estado = json.load(f)
    except (OSError, ValueError):
        estado = {}
    if os.environ.get("PRUEBA") == "1":
        whatsapp("*ZIP.​AI – vigía externo*\n\n✅ Prueba: el vigía externo está activo y revisa el portal cada 5 minutos.")
    for clave, nombre, url in VIGILADOS:
        e = estado.get(clave) or {}
        motivo = revisar(url)
        if motivo is None:
            print(f"{clave}: bien")
            if e.get("caido_desde"):
                if not e.get("avisado") or whatsapp(f"*ZIP.​AI – vigía externo*\n\n🟢 {nombre} volvió a responder a las "
                                                    f"{ahora():%H:%M}. Estuvo caído {duracion(e['caido_desde'])}."):
                    e = {}
            estado[clave] = e
            continue
        print(f"{clave}: MAL ({motivo})")
        if not e.get("caido_desde"):
            e = {"caido_desde": ahora().isoformat(), "avisado": False}
        ultimo = e.get("ultimo_aviso")
        if not e["avisado"] or (ultimo and ahora() - datetime.fromisoformat(ultimo) >= REPETIR_CADA):
            sigue = " Sigue caído." if e["avisado"] else ""
            if whatsapp(f"*ZIP.​AI – vigía externo*\n\n🔴 {nombre} no responde desde las {hora(e['caido_desde'])}: {motivo}.{sigue}\n\n"
                        "Puede ser la PC apagada o reiniciándose, sin internet, o el túnel o el servidor del portal caídos."):
                e["avisado"], e["ultimo_aviso"] = True, ahora().isoformat()
        estado[clave] = e
    os.makedirs(os.path.dirname(ESTADO), exist_ok=True)
    with open(ESTADO, "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False)


if __name__ == "__main__":
    main()
