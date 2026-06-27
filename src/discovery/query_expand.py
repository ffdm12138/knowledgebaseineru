"""Chinese/English query expansion for snow and boundary-layer literature."""
from src.library_index import VALID_DOMAINS


DOMAIN_TERMS = {
    "blowing_snow_physics": [
        "blowing snow",
        "snow particle",
        "snow sublimation",
        "snow fragmentation",
        "saltation",
        "suspension",
        "风吹雪",
        "吹雪",
        "雪粒",
        "升华",
        "破碎",
        "跃移",
        "悬移",
    ],
    "aeolian_snow_transport": [
        "aeolian transport",
        "snow transport",
        "sand transport",
        "saltation flux",
        "threshold friction velocity",
        "颗粒输运",
        "风沙",
        "风雪输运",
        "起动风速",
        "输沙率",
        "跃移通量",
    ],
    "abl_pbl": [
        "atmospheric boundary layer",
        "planetary boundary layer",
        "surface layer",
        "turbulence",
        "Monin Obukhov",
        "大气边界层",
        "行星边界层",
        "近地层",
        "湍流",
    ],
}


TERM_TRANSLATIONS = {
    "风吹雪": ["blowing snow", "drifting snow"],
    "吹雪": ["blowing snow", "drifting snow"],
    "升华": ["sublimation"],
    "破碎": ["fragmentation", "snow particle fragmentation"],
    "雪粒": ["snow particle"],
    "跃移": ["saltation"],
    "悬移": ["suspension"],
    "风沙": ["aeolian sand transport", "sand saltation"],
    "边界层": ["boundary layer", "atmospheric boundary layer"],
    "湍流": ["turbulence"],
    # 风雪/风沙颗粒过程与边界层补充术语
    "击溅": ["splash", "splash function", "particle splash"],
    "粒径分布": ["particle size distribution", "size distribution", "snow particle size distribution"],
    "大气边界层": ["atmospheric boundary layer", "ABL", "surface layer"],
    "行星边界层": ["planetary boundary layer", "PBL"],
    "地表剪切力": ["surface shear stress", "bed shear stress", "wall shear stress"],
    "摩阻风速": ["friction velocity", "u*", "shear velocity"],
    "起动": ["entrainment", "initiation of motion", "threshold"],
    "起动风速": ["threshold wind speed", "threshold friction velocity"],
    "输沙率": ["sand flux", "sediment transport rate", "saltation flux"],
    "风雪输运": ["blowing snow transport", "drifting snow transport", "snow saltation"],
}


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    out = []
    for value in values:
        key = value.strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(value.strip())
    return out


def expand_query(query: str, domain_id: str | None = None, max_queries: int = 8) -> dict:
    """Return original query, selected terms, and expanded search strings."""
    query = (query or "").strip()
    if not query:
        raise ValueError("query is required")
    if domain_id and domain_id not in VALID_DOMAINS:
        raise ValueError(f"invalid domain_id: {domain_id}")

    terms: list[str] = []
    for cn_term, translations in TERM_TRANSLATIONS.items():
        if cn_term in query:
            terms.extend(translations)
    if domain_id:
        terms.extend(DOMAIN_TERMS.get(domain_id, [])[:6])

    terms = _dedupe(terms)
    expanded = [query]
    if terms:
        expanded.append(" ".join(terms[:4]))
        expanded.append(f"{query} {' '.join(terms[:3])}")
    if domain_id:
        expanded.append(" ".join(DOMAIN_TERMS[domain_id][:4]))

    return {
        "original_query": query,
        "terms": terms,
        "expanded_queries": _dedupe(expanded)[:max_queries],
    }

