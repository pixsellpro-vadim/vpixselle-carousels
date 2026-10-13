# vpixselle-carousels

Автоматично робить слайди каруселей для Instagram (1080×1350) і TikTok (1080×1920) з черги Threads.

- `render.py` читає чергу (Google Sheets, опубліковану як CSV) і для кожного рядка зі статусом `queued` або `ad` робить 4 слайди.
- Ключ посту = `sha1(text.strip())`. Файли: `c/<ключ>/ig_1..4.jpg` і `tt_1..4.jpg`. Make рахує той самий ключ: `sha1(trim(text); "hex")`.
- GitHub Actions запускає рендер кожні 2 години і публікує папку `site/` на GitHub Pages.
- Налаштування: змінна репозиторію `QUEUE_CSV_URL` (Settings → Secrets and variables → Actions → Variables), Pages: Source = GitHub Actions.
