"""Append PayPal and Ko-fi links to every GitHub Pages article."""

_PAYPAL = (
    "https://www.paypal.com/donate/?business=P8CTXW8ER3PBY"
    "&no_recurring=0&item_name=Sponsor+My+Next+Bug&currency_code=EUR"
)

_DONATE = f"""
<section class="aio-donate">
  <h2>Donate</h2>
  <p>🤖 AI writes some code. I break it. We fix it together.</p>
  <p>Can’t spare a few bucks? Drop a star on GitHub instead. It feeds the ego, and that’s almost as good.</p>
  <p class="aio-donate__actions">
    <a class="md-button" href="{_PAYPAL}" target="_blank" rel="noopener noreferrer">PayPal</a>
    <a class="md-button" href="https://ko-fi.com/qballjos" target="_blank" rel="noopener noreferrer">Ko-fi</a>
  </p>
</section>
"""


def on_page_content(html, page, config, files):
    if 'class="aio-donate"' in html:
        return html
    return html + _DONATE
