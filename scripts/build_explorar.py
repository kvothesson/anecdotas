"""Genera los datos derivados que usa el explorador.

python scripts/build_explorar.py

data/explorar.json   lugar de cada episodio y sus episodios parecidos. Se carga al abrir.
data/busqueda.json   qué palabras se dicen en cada episodio. Se carga al primer uso del buscador.

Lee las transcripciones de data/episodes/*_raw.json, que no se publican. La salida guarda
palabras sueltas y no el texto, así el sitio no republica lo que se cuenta en los videos.
Correrlo después de ingestar episodios.
"""
import json
import math
import re
import unicodedata
from collections import Counter
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"

BUENOS_AIRES = {
    "AMBA", "Avellaneda", "Boulogne", "Buenos Aires", "Buenos Aires, Zona Oeste",
    "Ciudad Evita, Buenos Aires, Argentina", "Conurbano bonaerense", "Escobar, Buenos Aires, Argentina",
    "Florencia Varela", "Gran Buenos Aires, Argentina", "José C. Paz", "La Matanza", "La Matanza, Buenos Aires",
    "La Plata", "La Plata, Argentina", "Liniers", "Lomas de Zamora, Argentina", "Lomas del Mirador, Buenos Aires",
    "Longchamps", "Martínez", "Monte Chingolo, Buenos Aires, Argentina", "Moreno, Buenos Aires, Argentina",
    "Palermo", "Provincia de Buenos Aires", "Puerto Madero", "Ramos Mejía, Buenos Aires, Argentina", "Recoleta",
    "San Isidro", "San Martín", "San Miguel", "Tigre", "Villa Ballester", "Villa Ballester, Buenos Aires, Argentina",
    "Villa Domínico", "Zona Oeste, Buenos Aires, Argentina",
}
LATINOAMERICA = {
    "Ambato", "Anorí", "Antioquia", "Asunción", "Azogues", "Bogotá", "Bolivia", "Caleta San Marcos, Chile",
    "Canelones", "Caquetá", "Caracas", "Caribe", "Carmelo", "Chile", "Ciudad del Este, Paraguay", "Colombia",
    "Coroico", "Costa Rica", "Cuenca", "Ecuador", "Frutillar", "Hernandarias, Paraguay", "Ilha Grande, Brasil",
    "Iquique", "La Pedrera", "Montevideo", "México", "Osorno", "Paraguay", "Perú", "Playa del Carmen", "Pucón",
    "Puerto Rico", "Quito", "Reñaca, Chile", "Rurrenabaque", "San José", "San Pablo", "Santiago de Chile",
    "Sur de Chile", "Surinam", "Tigre, Venezuela", "Tulum", "Uruguay", "Uyuni", "Venezuela",
}
MUNDO = {
    "Alabama", "Alemania", "Argelia", "Arizona", "Armenia", "Atlanta", "Australia", "Austria", "Barcelona", "Berlín",
    "Budapest", "Bélgica", "Chicago", "Chipre", "Ciudad del Cabo", "Dubai", "España", "Estados Unidos", "Fez",
    "Formentera", "Francia", "Gold Coast, Australia", "Grecia", "Hungría", "Ibiza", "Imperio Otomano", "India",
    "Inglaterra", "Italia", "Japón", "Kioto", "Los Ángeles", "Mallorca", "Marruecos", "Medio Oriente", "Miami",
    "Moscú", "Módena, Italia", "Mónaco", "Múnich", "Niza", "Nueva York", "Nueva Zelanda", "París", "Palestina",
    "Qatar", "Roma", "Rusia", "Serbia", "Sudáfrica", "Texas", "Ámsterdam",
}
# "Argentina" a secas no dice dónde pasó: no cuenta para ningún lugar.
SIN_LUGAR = {"Argentina"}

PALABRAS_VACIAS = set("""
aca ahi ahora algo alguien algun alguna algunas alguno algunos alla alli ante antes aqui aquel aquella asi aun aunque
bajo bien cada casi cierto como con contra cosa cosas cual cuales cuando cuanto de del desde despues donde dos
durante ella ellas ello ellos entonces entre era eran eramos eres es esa esas ese eso esos esta estaba estaban estamos
estan estar estas este esto estos estoy fue fueron fui hace hacer hacia han has hasta hay haber habia hemos hizo
las les lo los mas me mi mia mientras mis mismo mucha muchas mucho muchos muy nada nadie ni no nos nosotros nunca
otra otras otro otros para pero poco por porque pues que quien quiere se sea segun ser si sido siempre sin sobre
solo son soy su sus tal tambien tan tanto te tener tengo tenia tiene tienen toda todas todo todos tres tu tus
una uno unos unas usted vamos van vez voy ya yo
""".split())


def normal(texto):
    sin_tildes = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in sin_tildes if unicodedata.category(c) != "Mn")


def palabras(texto):
    return [p for p in re.findall(r"[a-z]{4,}", normal(texto)) if p not in PALABRAS_VACIAS]


def lugares(ep):
    salida = set()
    for g in ep["analysis"]["geography"]:
        if g in SIN_LUGAR:
            continue
        if g in BUENOS_AIRES:
            salida.add("buenos-aires")
        elif g in LATINOAMERICA:
            salida.add("latinoamerica")
        elif g in MUNDO:
            salida.add("mundo")
        else:
            salida.add("interior")
    return sorted(salida)


def parecidas(eps, conteos, cuantas=6):
    """Coseno de TF-IDF sobre lo que se dice en cada episodio."""
    n = len(eps)
    df = Counter(p for c in conteos for p in c)
    idf = {p: math.log(n / d) for p, d in df.items() if 2 <= d <= n * 0.35}
    vectores = []
    for c in conteos:
        v = {p: (1 + math.log(f)) * idf[p] for p, f in c.items() if p in idf}
        largo = math.sqrt(sum(x * x for x in v.values())) or 1
        vectores.append({p: x / largo for p, x in v.items()})

    salida = {}
    for i, ep in enumerate(eps):
        puntajes = []
        for j, otro in enumerate(eps):
            if i == j:
                continue
            chico, grande = sorted((vectores[i], vectores[j]), key=len)
            s = sum(x * grande.get(p, 0) for p, x in chico.items())
            # Mismo tono y mismos temas pesan: una de terror llama a otra de terror.
            s *= 1.25 if ep["analysis"]["emotional_arc"] == otro["analysis"]["emotional_arc"] else 1
            s *= 1 + 0.05 * len(set(ep["analysis"]["categories"]) & set(otro["analysis"]["categories"]))
            puntajes.append((s, otro["id"]))
        puntajes.sort(reverse=True)
        salida[ep["id"]] = [i for _, i in puntajes[:cuantas]]
    return salida


def main():
    eps = json.loads((DATA / "index.json").read_text(encoding="utf-8"))
    conteos = []
    sin_texto = []
    for ep in eps:
        crudo = DATA / "episodes" / f"{ep['id']}_raw.json"
        texto = json.loads(crudo.read_text(encoding="utf-8")).get("transcript") if crudo.exists() else None
        if not texto:
            sin_texto.append(ep["episode_number"])
        conteo = Counter(palabras(texto or ""))
        # El resumen suma como si se repitiera: dice de qué trata mejor que la charla entera,
        # y cubre a los episodios sin transcripción.
        a = ep["analysis"]
        for p in palabras(" ".join([ep["title"], a["summary"], *a["archetypes"]])):
            conteo[p] += 3
        conteos.append(conteo)

    # Una palabra que aparece en casi todos los episodios no ayuda a encontrar ninguno.
    df = Counter(p for c in conteos for p in c)
    tope = len(eps) * 0.5
    indice = {}
    for i, c in enumerate(conteos):
        for p in c:
            if df[p] <= tope:
                indice.setdefault(p, []).append(i)

    explorar = {
        "lugares": {ep["id"]: lugares(ep) for ep in eps},
        "parecidas": parecidas(eps, conteos),
    }
    busqueda = {"ids": [ep["id"] for ep in eps], "palabras": dict(sorted(indice.items()))}
    (DATA / "explorar.json").write_text(json.dumps(explorar, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (DATA / "busqueda.json").write_text(json.dumps(busqueda, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    por_lugar = Counter(l for ls in explorar["lugares"].values() for l in ls)
    print(f"{len(eps)} episodios, {len(indice)} palabras, sin transcripción: {sin_texto or 'ninguno'}")
    print("lugares:", dict(por_lugar), "sin lugar:", sum(not ls for ls in explorar["lugares"].values()))
    for nombre in ("explorar", "busqueda"):
        print(nombre, round((DATA / f"{nombre}.json").stat().st_size / 1024), "KB")


if __name__ == "__main__":
    main()
