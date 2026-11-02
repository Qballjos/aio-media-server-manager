"""Append PayPal and Ko-fi links to every GitHub Pages article."""

from mkdocs import plugins

_PAYPAL = (
    "https://www.paypal.com/donate/?business=P8CTXW8ER3PBY"
    "&no_recurring=0&item_name=Sponsor+My+Next+Bug&currency_code=EUR"
)

# English lines stay the published wording. The others say the same thing.
_COPY = {
    "en": (
        "Donate",
        "🤖 AI writes some code. I break it. We fix it together.",
        "Can’t spare a few bucks? Drop a star on GitHub instead. It feeds the ego, and that’s almost as good.",
    ),
    "nl": (
        "Doneren",
        "🤖 AI schrijft wat code. Ik breek het. We lossen het samen op.",
        "Geen paar euro over? Geef dan een ster op GitHub. Dat voedt het ego, en dat is bijna net zo goed.",
    ),
    "de": (
        "Spenden",
        "🤖 KI schreibt etwas Code. Ich mache ihn kaputt. Wir reparieren ihn zusammen.",
        "Kein Kleingeld übrig? Geben Sie stattdessen einen Stern auf GitHub. Das füttert das Ego, und das ist fast genauso gut.",
    ),
    "fr": (
        "Faire un don",
        "🤖 L’IA écrit du code. Je le casse. On le répare ensemble.",
        "Pas quelques euros de côté ? Laissez une étoile sur GitHub. Ça nourrit l’ego, et c’est presque aussi bien.",
    ),
}

_TOGGLES = {
    "en": ("Switch to light mode", "Switch to dark mode", "Switch to system preference"),
    "nl": ("Naar lichte modus", "Naar donkere modus", "Systeemvoorkeur volgen"),
    "de": ("Zum hellen Modus", "Zum dunklen Modus", "Systemeinstellung folgen"),
    "fr": ("Passer au mode clair", "Passer au mode sombre", "Suivre le système"),
}


def _locale(page, config):
    file_locale = getattr(getattr(page, "file", None), "locale", None)
    if file_locale in _COPY:
        return file_locale
    theme = getattr(config, "theme", None)
    lang = ""
    if theme is not None:
        lang = str(theme.get("language") or "").split("-")[0]
    return lang if lang in _COPY else "en"


def _donate(locale):
    title, line_one, line_two = _COPY[locale]
    return f"""
<section class="aio-donate">
  <h2>{title}</h2>
  <p>{line_one}</p>
  <p>{line_two}</p>
  <p class="aio-donate__actions">
    <a class="md-button" href="{_PAYPAL}" target="_blank" rel="noopener noreferrer">PayPal</a>
    <a class="md-button" href="https://ko-fi.com/qballjos" target="_blank" rel="noopener noreferrer">Ko-fi</a>
  </p>
</section>
"""


@plugins.event_priority(-101)  # after mkdocs-static-i18n sets theme.language
def on_config(config):
    theme = getattr(config, "theme", None)
    if theme is None:
        return config
    lang = str(theme.get("language") or "en").split("-")[0]
    names = _TOGGLES.get(lang, _TOGGLES["en"])
    palette = theme.get("palette") or []
    if isinstance(palette, list):
        for entry, name in zip(palette, names):
            toggle = entry.get("toggle") if isinstance(entry, dict) else None
            if isinstance(toggle, dict):
                toggle["name"] = name
    return config


def on_page_content(html, page, config, files):
    if 'class="aio-donate"' in html:
        return html
    return html + _donate(_locale(page, config))
