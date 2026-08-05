from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .artifact_registry import ArtifactRegistry
from .case_manager import CaseManager
from .claims import ClaimRegistry
from .figure_registry import FigureRegistry
from .io_utils import atomic_write_json, atomic_write_text, now_iso


REQUIRED_SECTIONS = {
    "abstract",
    "problem_restated",
    "assumptions",
    "notation",
    "data_analysis",
    "model_construction",
    "model_solution",
    "results",
    "sensitivity",
    "strengths_weaknesses",
    "conclusion",
    "references",
}

# Optional sections that may be added for specific competition types
OPTIONAL_SECTIONS = {
    "momentum_analysis",
}

SECTION_CONTRACTS: dict[str, dict[str, list[list[str]]]] = {
    "abstract": {"required_any": [["研究目的", "研究目标"], ["研究方法", "方法"], ["主要结果", "结果"], ["稳健性", "边界"]]},
    "problem_restated": {"required_any": [["研究概述", "研究背景", "问题"], ["目标", "子问题"]]},
    "assumptions": {"required_any": [["假设"], ["适用", "边界"]]},
    "notation": {"required_any": [["$", "符号"], ["变量", "目标"]]},
    "data_analysis": {"required_any": [["数据", "字段"], ["缺失", "质量"]]},
    "model_construction": {"required_any": [["模型"], ["目标函数", "$", "损失"]]},
    "model_solution": {"required_any": [["求解", "训练"], ["交叉验证", "指标"]]},
    "results": {"required_any": [["结果", "模型"], ["图表证据", "图", "表"]]},
    "momentum_analysis": {"required_any": [["动量", "势头", "momentum"], ["假设检验", "Ljung-Box", "游程"], ["滑动窗口", "时序"]]},
    "sensitivity": {"required_any": [["敏感性", "稳健性"], ["比例", "随机种子", "波动"]]},
    "strengths_weaknesses": {"required_any": [["优点", "优势"], ["局限", "缺点"]]},
    "conclusion": {"required_any": [["结论"], ["适用", "外推", "限制"]]},
    "references": {"required_any": [["参考文献", "来源"]]},
}


def section_contract(section_id: str) -> dict[str, list[list[str]]]:
    return SECTION_CONTRACTS.get(section_id, {"required_any": []})


class SectionPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section_id: str = Field(min_length=2)
    title: str = Field(min_length=2)
    purpose: str = Field(min_length=3)
    claim_ids: list[str] = Field(default_factory=list)
    figure_ids: list[str] = Field(default_factory=list)
    required: bool = True


class PaperOutline(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    title: str = Field(min_length=3)
    language: Literal["zh", "en", "bilingual"] = "zh"
    competition_type: str = Field(min_length=2)
    sections: list[SectionPlan] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_sections(self) -> "PaperOutline":
        ids = [section.section_id for section in self.sections]
        if len(ids) != len(set(ids)):
            raise ValueError("section IDs must be unique")
        missing = REQUIRED_SECTIONS - set(ids)
        if missing:
            raise ValueError(f"required sections missing: {sorted(missing)}")
        return self


class PaperOutlineService:
    def __init__(
        self,
        cases: CaseManager,
        artifacts: ArtifactRegistry,
        claims: ClaimRegistry,
        figures: FigureRegistry,
    ) -> None:
        self.cases = cases
        self.artifacts = artifacts
        self.claims = claims
        self.figures = figures

    def validate_file(self, case_id: str, source_path: str | Path) -> dict:
        source = Path(source_path).resolve()
        outline = PaperOutline.model_validate_json(source.read_text(encoding="utf-8-sig"))
        known_claims = {claim["claim_id"]: claim for claim in self.claims.list_claims(case_id)}
        known_figures = {figure["figure_id"]: figure for figure in self.figures.list_figures(case_id)}
        errors: list[str] = []
        for section in outline.sections:
            for claim_id in section.claim_ids:
                if claim_id not in known_claims:
                    errors.append(f"unknown claim {claim_id} in {section.section_id}")
                elif known_claims[claim_id]["status"] != "VERIFIED":
                    errors.append(f"unverified claim {claim_id} in {section.section_id}")
            for figure_id in section.figure_ids:
                if figure_id not in known_figures:
                    errors.append(f"unknown figure {figure_id} in {section.section_id}")
                else:
                    artifact = self.artifacts.get(case_id, known_figures[figure_id]["artifact_id"])
                    if not artifact.get("paper_eligible", False):
                        errors.append(f"figure not paper ready {figure_id} in {section.section_id}")
        if errors:
            raise ValueError("; ".join(errors))
        root = self.cases.case_root(case_id)
        output_path = root / "paper" / "outline" / "outline.json"
        payload = {
            "schema_version": 1,
            "outline": outline.model_dump(mode="json"),
            "validated_at": now_iso(),
        }
        atomic_write_json(output_path, payload)
        artifact = self.artifacts.register_existing(
            case_id,
            output_path.relative_to(root).as_posix(),
            "paper_outline",
            "python",
            upstream=_outline_evidence(outline, known_claims, known_figures),
        )
        markdown_path = root / "paper" / "outline" / "outline.md"
        atomic_write_text(markdown_path, _render_outline(outline))
        markdown_artifact = self.artifacts.register_existing(
            case_id,
            markdown_path.relative_to(root).as_posix(),
            "paper_outline_preview",
            "python",
            upstream=[artifact["artifact_id"]],
        )
        return {
            "outline": payload,
            "outline_artifact_id": artifact["artifact_id"],
            "preview_artifact_id": markdown_artifact["artifact_id"],
        }


def default_outline(title: str, competition_type: str, language: str = "zh", problem_type: str = "") -> PaperOutline:
    definitions = [
        ("abstract", "摘要", "概括问题、方法、结果和关键词"),
        ("problem_restated", "引言与问题重述", "说明研究背景、题目价值，并准确重述题目目标与约束"),
        ("assumptions", "模型假设", "列出假设及其适用范围"),
        ("notation", "符号说明", "统一变量、参数和单位"),
        ("data_analysis", "数据分析", "说明来源、质量与探索性结果"),
        ("model_construction", "模型建立", "给出模型结构、公式和依据"),
        ("model_solution", "模型求解", "记录算法、参数和执行过程"),
        ("results", "结果分析", "基于已批准证据报告结果"),
    ]
    
    # Add momentum_analysis section for C-type competitions (time series/dynamic analysis)
    is_c_type = False
    if competition_type and len(competition_type) >= 2:
        # Check if competition type ends with 'C' or is exactly 'C' (MCM-C, ICM-C, etc.)
        comp_upper = competition_type.upper()
        if comp_upper == "C" or comp_upper.endswith("-C") or comp_upper.endswith("_C"):
            is_c_type = True
    # Also check problem_type parameter
    if problem_type and problem_type.lower() == "c":
        is_c_type = True
    
    if is_c_type:
        definitions.append(
            ("momentum_analysis", "动量分析", "分析势头存在性、假设检验、滑动窗口与发球方加权")
        )
    
    definitions.extend([
        ("sensitivity", "敏感性与稳健性", "报告敏感性门及限制"),
        ("strengths_weaknesses", "模型优缺点", "评价适用性与局限"),
        ("conclusion", "结论", "回答子问题并限制外推范围"),
        ("references", "参考文献", "列出可验证来源"),
    ])
    return PaperOutline(
        title=title,
        language=language,
        competition_type=competition_type,
        sections=[
            SectionPlan(section_id=identifier, title=section_title, purpose=purpose)
            for identifier, section_title, purpose in definitions
        ],
    )


def _outline_evidence(outline, claims, figures) -> list[str]:
    artifact_ids: list[str] = []
    for section in outline.sections:
        for claim_id in section.claim_ids:
            artifact_ids.extend(claims[claim_id]["evidence_artifact_ids"])
        for figure_id in section.figure_ids:
            artifact_ids.append(figures[figure_id]["artifact_id"])
    return list(dict.fromkeys(artifact_ids))


def _render_outline(outline: PaperOutline) -> str:
    lines = [f"# {outline.title}", ""]
    for index, section in enumerate(outline.sections, start=1):
        lines.extend(
            [
                f"## {index}. {section.title}",
                "",
                section.purpose,
                "",
                f"Claims: {', '.join(section.claim_ids) or 'None'}",
                "",
                f"Figures: {', '.join(section.figure_ids) or 'None'}",
                "",
            ]
        )
    return "\n".join(lines)
