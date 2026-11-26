# Bloque de servicios considerados abusables (RF-503).
# Cada elemento es un patrón de host o un host con prefijo de ruta '/'.
#
# Reglas de emparejamiento:
# - Patrón sin "/": coincide si host == patrón o host termina con "." + patrón
#   (límite de etiqueta). Ej.: "web.app" coincide con "x.web.app", no con "evilweb.app".
# - Patrón con "/": coincide si el host base (host == base o termina en "." + base)
#   y la ruta empieza con el prefijo. Ej.: "dropbox.com/s/" coincide con "dropbox.com/s/abc"
#   y con "x.dropbox.com/s/abc", no con "dropbox.com/pricing".


def _matches_abusable(host_or_url: str) -> bool:
    """Devuelve True si ``host_or_url`` coincide con algún patrón abusable.

    Reglas:
    - Patrón sin "/": host == patrón o host termina con "." + patrón.
    - Patrón con "/": el host base (host == base o termina en "." + base) y la ruta
      empieza con el prefijo.
    """
    value = host_or_url.lower()
    for pat in ABUSABLE_SERVICES:
        if "/" in pat:
            base, prefix = pat.split("/", 1)
            host = value.split("/", 1)[0]
            path = value.split("/", 1)[1] if "/" in value else ""
            if (host == base or host.endswith("." + base)) and path.startswith(prefix):
                return True
        else:
            if value == pat or value.endswith("." + pat):
                return True
    return False

ABUSABLE_SERVICES: tuple[str, ...] = (
    # Dominios completos de plataformas multi-inquilino/hosting (a)
    "docs.google.com",
    "drive.google.com",
    "sites.google.com",
    "forms.gle",
    "forms.office.com",
    "storage.googleapis.com",
    "s3.amazonaws.com",
    "notion.site",
    "firebaseapp.com",
    "web.app",
    "weebly.com",
    "windows.net",
    "sharepoint.com",
    "typeform.com",
    "secureserver.net",
    "sakura.ne.jp",
    "xdomain.jp",
    "nazwa.pl",
    "ovh.net",
    "oraclecloud.com",
    "wpengine.com",
    "cloudwaysapps.com",
    "myftpupload.com",
    "webcindario.com",
    "ferozo.com",
    "inmotionhosting.com",
    "flywheelsites.com",
    "activehosted.com",
    "googleusercontent.com",
    # Hosts (b)
    "translate.google.com",
    "script.google.com",
    # host+ruta (c)
    "linkedin.com/slink",
    "dropbox.com/s/",
    "duckdns.org",
    "no-ip.org",
    "ddns.net",
    "dropbox.com",
)

__all__ = ["ABUSABLE_SERVICES", "_matches_abusable"]
