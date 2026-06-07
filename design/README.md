# IELTS Anki Deck — Design

Thư mục này chứa toàn bộ **design system** cho bộ thẻ IELTS Anki:
file preview trực quan, tokens (màu, font, spacing), layout rules, và
template thật được bake vào `.apkg`.

## File map

| File | Vai trò | Khi nào mở |
| --- | --- | --- |
| **[`index.html`](./index.html)** | **Trang tổng quan** — show toàn bộ design system 1 chỗ. Class names khớp 100% với EAVM/styling.txt → là true preview của thẻ đã deploy. | **Bắt đầu ở đây** khi muốn xem design. |
| [`EAVM/`](./EAVM/) | **Source of truth** — `styling.txt`, `front_template.txt`, `back_template.txt`, `README.md`. Đây là những file được pack vào `.apkg`. | Khi muốn sửa design thật. |
| [`label_demo.html`](./label_demo.html) | Demo 6 case của label system (register tags, subject labels, corpus badges, footer badges) có annotation bên cạnh. | Khi cần xem chi tiết cách parser xử lý `[tag] text`. |
| [`card_design.html`](./card_design.html) | Phiên bản preview cũ hơn — 3 card mẫu (Oxford deck + AWL deck) với CEFR palette. | Legacy — giữ lại làm tham chiếu, nội dung đã được gộp vào `index.html`. |
| [`oxford_labels_full_taxonomy.html`](./oxford_labels_full_taxonomy.html) | Reference đầy đủ 17 nhãn chính thức của Oxford Learner's Dictionary + 6 corpus symbols + 22 subject labels. | Khi cần tra cứu tag nào thuộc nhóm nào. |

## Quick start

1. Mở [`index.html`](./index.html) trong browser → xem toàn bộ design system.
2. Muốn sửa giao diện thẻ → sửa file trong [`EAVM/`](./EAVM/).
3. Xem [EAVM/README.md](./EAVM/README.md) để biết cơ chế tự động build `.apkg` từ các file này.

## Design tokens (quick reference)

### Color palette

| Token | Hex | Dùng cho |
| --- | --- | --- |
| `bg-card` | `#141313` | Nền card |
| `bg-section` | `#1c1b1b` | Nền section box |
| `bg-elevated` | `#252424` | Nền chip nổi (collocation) |
| `border-default` | `#2a2929` | Viền card |
| `border-subtle` | `#282727` | Viền section |
| `text-primary` | `#e5e2e1` | Word, definition |
| `text-secondary` | `#c4c7c7` | Example, label |
| `text-meta` | `#8e9192` | IPA, section title |
| `accent-purple` | `#a78bfa` | Số thứ tự, pos-chip-num, word family |
| `accent-amber` | `#fb923c` | Register tag — attitude |
| `accent-warm` | `#fbbf24` | Register tag — slang/specialist |
| `accent-red` | `#fca5a5` | Register tag — offensive/taboo |
| `accent-subject` | `#c4b5fd` | Subject label (OLDAE) |
| `cefr-A1` | `#5eead4` | CEFR A1 |
| `cefr-A2` | `#67e8f9` | CEFR A2 |
| `cefr-B1` | `#93c5fd` | CEFR B1 |
| `cefr-B2` | `#c4b5fd` | CEFR B2 |
| `cefr-C1` | `#fcd34d` | CEFR C1 |
| `cefr-C2` | `#fda4af` | CEFR C2 |
| `cefr-UNCLASSIFIED` | `#c4c7c7` | Không phân loại |

### Typography

- **Sans** (body, word, definition): `Hanken Grotesk`, fallback `-apple-system, sans-serif`
- **Mono** (chip, label, IPA, badge): `JetBrains Mono`, fallback `monospace`
- **Icons**: `Tabler Icons` (CDN)

### Spacing

- Card padding: `24–28px`
- Section gap: `16px`
- Border radius: `20px` (card), `16px` (section box), `9999px` (chip/badge), `6px` (corpus badge)
- Card width: `360px` (preview) / `max-width: 540px` (Anki)

## Quy tắc chỉnh sửa

> **Mọi thay đổi design phải bắt đầu từ `EAVM/`.**

1. Sửa `EAVM/styling.txt` (CSS), `EAVM/front_template.txt` (HTML mặt trước), hoặc `EAVM/back_template.txt` (HTML mặt sau).
2. Chạy script `update_anki_deck.py` để bake thành `.apkg`.
3. Sync lại preview bằng cách copy CSS từ `EAVM/styling.txt` vào `<style>` của `index.html` / `card_design.html` / `label_demo.html`.

> [!WARNING]
> **JS newline gotcha**: Anki's JS engine crash nếu có literal newline trong string. Xem [EAVM/README.md § Lưu ý quan trọng khi chỉnh sửa JavaScript](./EAVM/README.md#lưu-ý-quan-trọng-khi-chỉnh-sửa-javascript).

## Liên kết

- Source code Python: [`update_anki_deck.py`](../update_anki_deck.py) (ở root)
- Vocab lists: [`../vocab_list/`](../vocab_list/)
- Data: [`../data/`](../data/)
