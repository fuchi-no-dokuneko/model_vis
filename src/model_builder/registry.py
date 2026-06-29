from __future__ import annotations

import inspect
import re
from dataclasses import asdict, dataclass
from functools import lru_cache
from typing import Any, Iterable

from .catalog import CatalogEntry
from .util import sha256_json


COMPACT_PROFILE_VERSION = 22

MODEL_CLASS_OVERRIDES = {
    "chmv2": "CHMv2ForDepthEstimation",
    "depth_anything": "DepthAnythingForDepthEstimation",
    "eomt": "EomtForUniversalSegmentation",
    "eomt_dinov3": "EomtDinov3ForUniversalSegmentation",
    "prompt_depth_anything": "PromptDepthAnythingForDepthEstimation",
    "superglue": "SuperGlueForKeypointMatching",
    "superpoint": "SuperPointForKeypointDetection",
    "upernet": "UperNetForSemanticSegmentation",
    "videomt": "VideomtForUniversalSegmentation",
    "vitmatte": "VitMatteForImageMatting",
    "vitpose": "VitPoseForPoseEstimation",
    "zoedepth": "ZoeDepthForDepthEstimation",
    "pop2piano": "Pop2PianoForConditionalGeneration",
}


def _normal(value: str) -> str:
    value = re.sub(r"\b(and|with)\b", "", value.lower())
    value = value.replace("configuration", "").replace("config", "").replace("model", "")
    return re.sub(r"[^a-z0-9]", "", value)


# Display aliases documented by Transformers/Diffusers but not represented by
# their Python config/class names. A value may expand one catalog family into
# several concrete architecture versions.
ALIASES: dict[str, tuple[tuple[str, str], ...]] = {
    "BARThez": (("transformers", "bart"),),
    "BARTpho": (("transformers", "bart"),),
    "BertJapanese": (("transformers", "bert"),),
    "BERTweet": (("transformers", "roberta"),),
    "ByT5": (("transformers", "t5"),),
    "CodeLlama": (("transformers", "llama"),),
    "CPM": (("transformers", "cpmant"),),
    "DialoGPT": (("transformers", "gpt2"),),
    "Encoder Decoder Models": (("transformers", "encoder-decoder"),),
    "EXAONE-4.0": (("transformers", "exaone4"),),
    "Falcon3": (("transformers", "falcon"),),
    "FLAN-T5": (("transformers", "t5"),),
    "FLAN-UL2": (("transformers", "t5"),),
    "Funnel Transformer": (("transformers", "funnel"),),
    "GLM-4-0414": (("transformers", "glm4"),),
    "GLM-4.5, GLM-4.6, GLM-4.7": (
        ("transformers", "glm4_moe"),
        ("transformers", "glm4_moe"),
        ("transformers", "glm4_moe"),
    ),
    "GLM-4.7-Flash": (("transformers", "glm4_moe"),),
    "GPT": (("transformers", "openai-gpt"),),
    "HerBERT": (("transformers", "bert"),),
    "Llama2": (("transformers", "llama"),),
    "Llama3": (("transformers", "llama"),),
    "MADLAD-400": (("transformers", "t5"),),
    "MarianMT": (("transformers", "marian"),),
    "MBart and MBart-50": (("transformers", "mbart"),),
    "MegatronGPT2": (("transformers", "gpt2"),),
    "mLUKE": (("transformers", "luke"),),
    "myt5": (("transformers", "t5"),),
    "NLLB": (("transformers", "m2m_100"),),
    "Nyströmformer": (("transformers", "nystromformer"),),
    "PhoBERT": (("transformers", "roberta"),),
    "T5v1.1": (("transformers", "t5"),),
    "UL2": (("transformers", "t5"),),
    "XLM-V": (("transformers", "xlm-roberta"),),
    "Youtu-LLM": (("transformers", "youtu"),),
    "Depth Anything V2": (("transformers", "depth_anything"),),
    "DINOv2 with Registers": (("transformers", "dinov2_with_registers"),),
    "DINOv3": (("transformers", "dinov3_vit"),),
    "DiT": (("diffusers", "DiTTransformer2DModel"),),
    "Pyramid Vision Transformer (PVT)": (("transformers", "pvt"),),
    "Pyramid Vision Transformer v2 (PVTv2)": (("transformers", "pvt_v2"),),
    "Segment Anything": (("transformers", "sam"),),
    "Segment Anything High Quality": (("transformers", "sam_hq"),),
    "Swin Transformer": (("transformers", "swin"),),
    "Swin Transformer V2": (("transformers", "swinv2"),),
    "Vision Transformer (ViT)": (("transformers", "vit"),),
    "LASR": (("transformers", "lasr_ctc"),),
    "MMS": (("transformers", "wav2vec2"),),
    "Parakeet": (("transformers", "parakeet_tdt"),),
    "Wav2Vec2Phoneme": (("transformers", "wav2vec2"),),
    "XLS-R": (("transformers", "wav2vec2"),),
    "XLSR-Wav2Vec2": (("transformers", "wav2vec2"),),
    "Code World Model (CWM)": (("transformers", "cwm"),),
    "Data2Vec": (
        ("transformers", "data2vec-text"),
        ("transformers", "data2vec-audio"),
        ("transformers", "data2vec-vision"),
    ),
    "DePlot": (("transformers", "pix2struct"),),
    "Donut": (("transformers", "vision-encoder-decoder"),),
    "GraniteVision": (("transformers", "granite4_vision"),),
    "MatCha": (("transformers", "pix2struct"),),
    "MiniCPM-V": (("transformers", "minicpmv4_6"),),
    "Speech Encoder Decoder Models": (("transformers", "speech-encoder-decoder"),),
    "Vision Encoder Decoder Models": (("transformers", "vision-encoder-decoder"),),
    "Oobleck AutoEncoder": (("diffusers", "AutoencoderOobleck"),),
    "Tiny AutoEncoder": (("diffusers", "AutoencoderTiny"),),
    "UViT2DModel": (("diffusers", "UVit2DModel"),),
}


@dataclass(frozen=True)
class ResolvedVersion:
    family_id: str
    family_name: str
    category: str
    version_id: str
    display_name: str
    library: str
    architecture_key: str
    config_class: str | None
    entrypoint_module: str
    entrypoint_class: str
    task_type: str
    structure_key: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@lru_cache(maxsize=1)
def _transformer_indexes() -> tuple[dict[str, tuple[str, str]], dict[str, str]]:
    from transformers.models.auto.configuration_auto import CONFIG_MAPPING_NAMES
    from transformers.models.auto.modeling_auto import MODEL_MAPPING_NAMES

    names: dict[str, tuple[str, str]] = {}
    for model_type, config_name in CONFIG_MAPPING_NAMES.items():
        names.setdefault(_normal(model_type), (model_type, config_name))
        names.setdefault(_normal(config_name), (model_type, config_name))
    return names, dict(MODEL_MAPPING_NAMES)


def _task_type(category: str) -> str:
    return {
        "Vision models": "vision",
        "Audio models": "audio",
        "Video models": "vision",
        "Multimodal models": "multimodal",
        "Reinforcement learning models": "custom",
        "UNets": "diffusion",
        "VAEs": "diffusion",
    }.get(category, "text")


def _transformer_version(entry: CatalogEntry, model_type: str, ordinal: int) -> ResolvedVersion:
    from transformers.models.auto.configuration_auto import CONFIG_MAPPING_NAMES

    _, model_names = _transformer_indexes()
    if model_type not in CONFIG_MAPPING_NAMES:
        raise KeyError(f"Transformers config key {model_type!r} is unavailable for {entry.display_name}")
    config_class = CONFIG_MAPPING_NAMES[model_type]
    model_class = model_names.get(model_type)
    if isinstance(model_class, (tuple, list)):
        model_class = model_class[0]
    if not model_class:
        # Composite configs are handled by a generic adapter in factory.py.
        model_class = config_class.removesuffix("Config") + "Model"
    model_class = MODEL_CLASS_OVERRIDES.get(model_type, model_class)
    module_name = model_type.replace("-", "_")
    suffix = f"-{ordinal + 1}" if ordinal else ""
    signature = {
        "library": "transformers",
        "config_class": config_class,
        "model_class": model_class,
        "compact_profile": COMPACT_PROFILE_VERSION,
    }
    return ResolvedVersion(
        family_id=entry.family_id,
        family_name=entry.display_name,
        category=entry.category,
        version_id=f"{entry.family_id}{suffix}",
        display_name=entry.display_name if not ordinal else f"{entry.display_name} {ordinal + 1}",
        library="transformers",
        architecture_key=model_type,
        config_class=config_class,
        entrypoint_module=f"transformers.models.{module_name}.modeling_{module_name}",
        entrypoint_class=model_class,
        task_type=_task_type(entry.category),
        structure_key="sha256." + sha256_json(signature),
    )


def _diffusers_version(entry: CatalogEntry, class_name: str, ordinal: int) -> ResolvedVersion:
    import diffusers

    model_class = getattr(diffusers, class_name, None)
    if not inspect.isclass(model_class):
        raise KeyError(f"Diffusers class {class_name!r} is unavailable for {entry.display_name}")
    signature = {
        "library": "diffusers",
        "model_class": class_name,
        "compact_profile": COMPACT_PROFILE_VERSION,
    }
    suffix = f"-{ordinal + 1}" if ordinal else ""
    return ResolvedVersion(
        family_id=entry.family_id,
        family_name=entry.display_name,
        category=entry.category,
        version_id=f"{entry.family_id}{suffix}",
        display_name=entry.display_name if not ordinal else f"{entry.display_name} {ordinal + 1}",
        library="diffusers",
        architecture_key=class_name,
        config_class=None,
        entrypoint_module=model_class.__module__,
        entrypoint_class=class_name,
        task_type="diffusion",
        structure_key="sha256." + sha256_json(signature),
    )


def resolve_entry(entry: CatalogEntry) -> tuple[ResolvedVersion, ...]:
    targets = ALIASES.get(entry.display_name)
    if targets is None:
        index, _ = _transformer_indexes()
        match = index.get(_normal(entry.display_name))
        if match:
            targets = (("transformers", match[0]),)
        else:
            # Diffusers entries in model.txt use their public class names.
            targets = (("diffusers", entry.display_name),)

    versions: list[ResolvedVersion] = []
    for ordinal, (library, key) in enumerate(targets):
        if library == "transformers":
            versions.append(_transformer_version(entry, key, ordinal))
        else:
            versions.append(_diffusers_version(entry, key, ordinal))
    return tuple(versions)


def resolve_catalog(entries: Iterable[CatalogEntry]) -> tuple[ResolvedVersion, ...]:
    versions: list[ResolvedVersion] = []
    errors: list[str] = []
    for entry in entries:
        try:
            versions.extend(resolve_entry(entry))
        except (AttributeError, ImportError, KeyError) as exc:
            errors.append(f"line {entry.line_number}: {entry.display_name}: {exc}")
    if errors:
        raise ValueError("catalog registry resolution failed:\n" + "\n".join(errors))
    return tuple(versions)
