from __future__ import annotations

from mathworkstation.paper_layout_ir import PaperLayoutIRBuilder


def test_builder_preserves_document_semantics_as_blocks() -> None:
    markdown = """# Demo Paper

# 摘要

这是摘要。

# 1. 模型

正文。

$$
x+y=1
$$

![图1 示例](../../figures/demo.png)

| A | B |
|---|---|
| 1 | 2 |

- 一
- 二
"""
    ir = PaperLayoutIRBuilder().build(markdown)
    assert ir.title == "Demo Paper"
    kinds = [block.kind for block in ir.blocks]
    assert "display_math" in kinds
    assert "figure" in kinds
    assert "table" in kinds
    assert "bullet_list" in kinds
    figure = next(block for block in ir.blocks if block.kind == "figure")
    assert figure.path == "../../figures/demo.png"
    assert figure.intent.width_fraction == 0.92


def test_heading_blocks_are_kept_with_following_content() -> None:
    ir = PaperLayoutIRBuilder().build("# Demo\n\n## 1.1 Core model\nText")
    headings = [block for block in ir.blocks if block.kind == "heading"]
    assert headings
    assert all(block.intent.keep_with_next for block in headings)
