# IELTS Anki Deck — Design

Thư mục này chứa toàn bộ **design system** cho bộ thẻ IELTS Anki:
file preview trực quan, tokens (màu, font, spacing), layout rules, và
template thật được bake vào `.apkg`.

## File map

| File | Vai trò | Khi nào mở |
| --- | --- | --- |
| **[`index.html`](./index.html)** | **Source of truth** — trang tổng quan show toàn bộ design system. Class names là immutable contract. Vùng 2 (line 197 → trước `END ANKI CARD STYLES`) là card CSS được sync vào `EAVM/styling.txt`. | **Bắt đầu ở đây** khi muốn xem hoặc sửa design. |
| [`EAVM/`](./EAVM/) | **Implementation** — `styling.txt`, `front_template.txt`, `back_template.txt`, `README.md`. Đây là những file được pack vào `.apkg`. | Khi muốn sửa template HTML/JS hoặc sửa CSS thẳng (không qua design review). |
| [`oxford_labels_full_taxonomy.html`](./oxford_labels_full_taxonomy.html) | Reference đầy đủ 17 nhãn chính thức của Oxford Learner's Dictionary + 6 corpus symbols + 22 subject labels. | Khi cần tra cứu tag nào thuộc nhóm nào. |
| [`../../tools/check_design_sync.py`](../../tools/check_design_sync.py) | CLI drift check — so sánh vùng 2 của `index.html` với `EAVM/styling.txt`. | Trước khi commit thay đổi CSS, hoặc khi CI fail. |
| [`../../tests/design/test_design_sync.py`](../../tests/design/test_design_sync.py) | Pytest version — chạy cùng parser, fail nếu drift. | Tự động trong `pytest` / CI. |

## Quick start

1. Mở [`index.html`](./index.html) trong browser → xem toàn bộ design system.
2. Muốn sửa design → sửa `index.html` (vùng 2) trước, sync `EAVM/styling.txt` cho khớp.
3. Chạy `python -m tools.check_design_sync` (hoặc `pytest tests/design/`) để confirm không drift.
4. Chạy `update_anki_deck.py` (root) để bake `.apkg`.

## Design tokens (quick reference)

Giá trị dưới đây là **sau khi sync** (mirror vùng 2 của `index.html` + `EAVM/styling.txt`).
Để refresh, đọc thẳng từ `EAVM/styling.txt` — drift check sẽ flag nếu lệch.

### Color palette

| Token | Hex | Dùng cho |
| --- | --- | --- |
| `bg-card` | `#141313` | Nền card |
| `bg-section` | `#181717` | Nền section box |
| `bg-elevated` | `#1e1d1d` | Nền collocation chip |
| `bg-word-family` | `#131226` | Nền word-family box |
| `border-default` | `#2a2929` | Viền card |
| `border-subtle` | `#252424` | Viền section |
| `border-word-family` | `#2d2460` | Viền word-family box |
| `text-primary` | `#f1f5f9` | Word (front + back) |
| `text-def` | `#e2e8f0` | Definition, sense-def |
| `text-secondary` | `#c4c7c7` | POS chip, top-badge (CEFR) |
| `text-meta` | `#94a3b8` | IPA pill, audio btn |
| `text-muted` | `#64748b` | Sense-ex, usage-tag |
| `text-section-title` | `#4b5563` | Section title |
| `accent-purple` | `#a78bfa` | Số thứ tự (pos-chip-num, sense-num) |
| `accent-amber` | `#fb923c` | Register tag — attitude (`rt-amber`) |
| `accent-warm` | `#fbbf24` | Register tag — slang/specialist (`rt-warm`) |
| `accent-red` | `#fca5a5` | Register tag — offensive/taboo (`rt-red`) |
| `accent-subject` | `#c4b5fd` | Subject label (`rt-subject`), word-family-word |
| `cefr-A1` | `#5eead4` | CEFR A1 |
| `cefr-A2` | `#67e8f9` | CEFR A2 |
| `cefr-B1` | `#93c5fd` | CEFR B1 |
| `cefr-B2` | `#c4b5fd` | CEFR B2 |
| `cefr-C1` | `#fcd34d` | CEFR C1 |
| `cefr-C2` | `#fda4af` | CEFR C2 |
| `cefr-UNCLASSIFIED` | `#c4c7c7` | Không phân loại |
| `wf-pos-n` (teal) | `#5eead4` | Word-family chip — noun |
| `wf-pos-v` (blue) | `#93c5fd` | Word-family chip — verb |
| `wf-pos-adj` (purple) | `#a78bfa` | Word-family chip — adjective |
| `wf-pos-adv` (amber) | `#fbbf24` | Word-family chip — adverb |
| `wf-pos-phr` (orange) | `#fb923c` | Word-family chip — phrase |
| `wf-pos-prep` (green) | `#86efac` | Word-family chip — preposition |

### Typography

- **Sans** (body, word, definition, register-tag): `Hanken Grotesk`, fallback `-apple-system, sans-serif`
- **Mono** (chip, label, badge, corpus, wf, audio btn, section title): `JetBrains Mono`, fallback `monospace`
- **IPA** (`.ipa-text` only): `Charis SIL`, `Doulos SIL`, `Segoe UI`, `Lucida Sans Unicode`, `Arial Unicode MS`, `sans-serif` — dùng cascade font hệ thống + font SIL chuyên IPA. Không embed base64; phụ thuộc font user đã cài (Charis/Doulos SIL nếu có, fallback Segoe UI/Lucida/Arial Unicode MS nếu không). Cross-platform an toàn, IPA glyphs (ɪ/ʃ/ˈ) render đúng ở hầu hết môi trường.
- **Icons**: `Tabler Icons` (CDN)

### Spacing

- Card content padding: `28px 20px` (back) / `40px` (front)
- Section gap (back content): `20px`
- Border radius: `20px` (card), `14px` (section box), `9999px` (chip/badge), `6px` (corpus badge), `3px` (sense-num / pos-chip-num)
- Card width: `440px` fixed (preview) / `100%` (Anki, max 540px) — marked `/* @preview-only */` cho width

## Quy tắc chỉnh sửa

> **Mọi thay đổi design bắt đầu từ `index.html` (vùng 2).**
> `EAVM/styling.txt` và `EAVM/*.txt` derive từ đó.

1. Sửa `index.html` vùng 2 (giữa `ANKI CARD STYLES` và `END ANKI CARD STYLES`). **Không đổi tên class** — class names là immutable contract.
2. Nếu thêm rule mà không muốn sync vào Anki (preview-only), đặt `/* @preview-only */` ngay phía trước rule.
3. Sync `EAVM/styling.txt` theo cùng selector + property.
4. Chạy `python -m tools.check_design_sync` — nếu OK, proceed; nếu drift, fix.
5. Chạy `update_anki_deck.py` để bake `.apkg`.

> [!WARNING]
> **JS newline gotcha**: Anki's JS engine crash nếu có literal newline trong string. Xem [EAVM/README.md § Lưu ý quan trọng khi chỉnh sửa JavaScript](./EAVM/README.md#lưu-ý-quan-trọng-khi-chỉnh-sửa-javascript).

## Drift check

- **CLI**: `python -m tools.check_design_sync` — exit 0 nếu sync, exit 1 nếu drift (in ra diff).
- **Pytest**: `pytest tests/design/test_design_sync.py` — chạy cùng parser, fail nếu drift.
- **CI**: thêm `pytest tests/design/` vào workflow. Drift = red build.

> **Preview-only selectors** (`.anki-card-container`, `.card-content-front`): đánh dấu `/* @preview-only */` trong `index.html` vì chúng có property cố ý khác production (width, min-height). Drift check sẽ skip cả rule.

## Liên kết

- Source code Python: [`update_anki_deck.py`](../update_anki_deck.py) (ở root, owned by `developer` rein)
- Vocab lists: [`../vocab_list/`](../vocab_list/) (owned by `scraper` rein)
- Data: [`../data/`](../data/) (owned by `deck-builder` rein)
- Top-level team conventions: [`../AGENTS.md`](../AGENTS.md)
