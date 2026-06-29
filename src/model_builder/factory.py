from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any

import torch
from torch import nn

from .registry import ResolvedVersion


COMPACT_VALUES: dict[str, Any] = {
    "vocab_size": 64,
    "hidden_size": 16,
    "d_model": 16,
    "dim": 16,
    "embed_dim": 16,
    "embedding_size": 16,
    "intermediate_size": 32,
    "ffn_dim": 32,
    "encoder_ffn_dim": 32,
    "decoder_ffn_dim": 32,
    "num_hidden_layers": 1,
    "num_layers": 1,
    "n_layer": 1,
    "encoder_layers": 1,
    "decoder_layers": 1,
    "num_attention_heads": 4,
    "num_heads": 4,
    "n_head": 4,
    "encoder_attention_heads": 4,
    "decoder_attention_heads": 4,
    "num_key_value_heads": 2,
    "head_dim": 4,
    "max_position_embeddings": 32,
    "n_positions": 32,
    "max_sequence_length": 32,
    "seq_length": 8,
    "image_size": 16,
    "input_size": 16,
    "patch_size": 4,
    "num_channels": 3,
    "in_channels": 3,
    "out_channels": 3,
    "sample_size": 16,
    "audio_length": 32,
    "num_mel_bins": 16,
    "feature_size": 16,
    "max_source_positions": 32,
    "max_target_positions": 32,
    "num_experts": 2,
    "num_local_experts": 2,
    "num_experts_per_tok": 1,
    "top_k": 1,
    "depths": 1,
    "hidden_sizes": 16,
    "embed_dims": 16,
    "block_out_channels": 16,
    "layers_per_block": 1,
    "num_hidden_groups": 1,
    "inner_group_num": 1,
    "type_vocab_size": 2,
    "state_dim": 4,
    "act_dim": 2,
    "norm_num_groups": 4,
    "hidden_size_global": 16,
    "encoder_hash_byte_group_vocab": 64,
    "rotary_dim": 4,
    "mamba_n_heads": 4,
    "mamba_d_head": 4,
    "mamba_d_state": 4,
    "mamba_d_conv": 2,
    "mamba_expand": 1,
    "mamba_chunk_size": 4,
    "qk_rope_head_dim": 2,
    "qk_nope_head_dim": 2,
    "qk_head_dim": 4,
    "v_head_dim": 4,
    "kv_lora_rank": 4,
    "q_lora_rank": 4,
    "o_lora_rank": 4,
    "index_n_heads": 2,
    "index_head_dim": 4,
    "moe_intermediate_size": 16,
    "n_shared_experts": 1,
    "n_routed_experts": 2,
    "moe_num_experts": 2,
    "block_sizes": 1,
    "block_repeats": 1,
    "output_channels": 16,
    "out_hidden_size": 16,
    "image_token_id": 1,
    "video_token_id": 2,
    "image_start_token_id": 3,
    "image_end_token_id": 4,
    "partial_rotary_factor": 0.5,
    "ffn_hidden_size": 32,
    "downsample_channels": 16,
    "mamba_d_ssm": 16,
    "depth": 1,
    "latent_channels": 16,
    "ch": 16,
    "num_embeddings": 64,
    "vision_vocab_size": 64,
    "n_groups": 1,
    "projector_hidden_size": 16,
    "expand": 1,
    "state_size": 4,
    "time_step_rank": 4,
    "chunk_size": 4,
    "linear_key_head_dim": 4,
    "linear_value_head_dim": 4,
    "linear_num_key_heads": 4,
    "linear_num_value_heads": 4,
    "shared_expert_intermediate_size": 16,
    "n_docs": 1,
    "num_groups": 4,
    "embedding_dim": 16,
    "attention_hidden_size": 16,
    "attention_head_dim": 4,
    "n_mamba_heads": 4,
    "mamba_ngroups": 1,
    "mamba_headdim": 4,
    "kv_channels": 4,
    "num_query_groups": 4,
    "mamba_dt_rank": 4,
    "cross_attention_hidden_size": 16,
    "encoder_hidden_dim": 16,
    "encoder_in_channels": 16,
    "decoder_in_channels": 16,
    "fusion_hidden_size": 16,
    "intermediate_feature_dims": 16,
    "scaled_images_feature_dims": 16,
    "mm_tokens_per_image": 4,
    "boi_token_index": 2,
    "eoi_token_index": 3,
    "stage_in_channels": 16,
    "stage_out_channels": 16,
    "stage_mid_channels": 16,
    "neck_hidden_sizes": 16,
    "reassemble_hidden_size": 16,
    "post_process_channels": 16,
    "head_hidden_size": 16,
    "number_output_channels": 16,
    "num_queries": 4,
    "num_denoising": 4,
    "max_num_bins": 8,
    "window_size": 2,
    "input_feat_per_channel": 16,
    "feature_projection_input_dim": 16,
    "audio_feature_size": 16,
    "input_dim": 16,
    "conv_dim": 16,
    "conv_kernel": 3,
    "conv_stride": 2,
    "conv_channels": 16,
    "audio_token_id": 1,
    "audio_eos_token_id": 2,
    "audio_pad_token_id": 0,
}


@dataclass
class ModelBundle:
    model: nn.Module
    inputs: tuple[Any, ...]
    kwargs: dict[str, Any]
    config: dict[str, Any]


def _compact_config(config: Any, seen: set[int] | None = None) -> Any:
    from transformers import PretrainedConfig

    seen = seen or set()
    if id(config) in seen:
        return config
    seen.add(id(config))

    for name, value in COMPACT_VALUES.items():
        if hasattr(config, name):
            try:
                current = getattr(config, name)
                if isinstance(current, tuple):
                    value = tuple(value for _ in current)
                elif isinstance(current, list):
                    value = [value for _ in current]
                setattr(config, name, value)
            except (AttributeError, TypeError, ValueError, NotImplementedError):
                pass
    for name, value in vars(config).items():
        if isinstance(value, PretrainedConfig):
            _compact_config(value, seen)
        elif isinstance(value, dict) and name.endswith("_config"):
            for key, compact in COMPACT_VALUES.items():
                if key in value:
                    value[key] = compact
    # Keep coupled dimensions internally valid.
    for width_name in ("hidden_size", "d_model", "dim", "embed_dim"):
        width = getattr(config, width_name, None)
        if isinstance(width, int):
            for heads_name in ("num_attention_heads", "num_heads", "n_head"):
                heads = getattr(config, heads_name, None)
                if isinstance(heads, int) and width % heads:
                    setattr(config, heads_name, 1)
    vocab_size = getattr(config, "vocab_size", None)
    if isinstance(vocab_size, int) and vocab_size > 1:
        for token_name in (
            "bos_token_id", "eos_token_id", "decoder_start_token_id", "sep_token_id",
            "cls_token_id", "mask_token_id",
        ):
            if hasattr(config, token_name) and getattr(config, token_name) is not None:
                setattr(config, token_name, 1)
        if hasattr(config, "pad_token_id"):
            config.pad_token_id = 0
    if hasattr(config, "use_cache"):
        config.use_cache = False
    if hasattr(config, "mrope_section"):
        head_width = int(getattr(config, "hidden_size", 16)) // int(getattr(config, "num_attention_heads", 4))
        half_width = max(1, head_width // 2)
        sections = [0] * len(config.mrope_section)
        for index in range(half_width):
            sections[index % len(sections)] += 1
        config.mrope_section = sections
    if getattr(config, "model_type", None) == "glm_image_text":
        config.rope_parameters["mrope_section"] = [1, 1, 0]
    layer_count = int(getattr(config, "num_hidden_layers", 1))
    for name in ("layer_types", "mlp_layer_types", "indexer_types"):
        if hasattr(config, name):
            current = getattr(config, name)
            if current is None:
                default_type = "dense" if name == "mlp_layer_types" else "full_attention"
                setattr(config, name, [default_type] * layer_count)
            elif isinstance(current, (list, tuple)) and current:
                try:
                    setattr(config, name, type(current)([current[0]] * layer_count))
                except (AttributeError, TypeError, ValueError):
                    pass
    if hasattr(config, "encoder_config") and hasattr(config, "global_config"):
        encoder = config.encoder_config
        global_config = config.global_config
        if hasattr(encoder, "hidden_size") and hasattr(global_config, "encoder_cross_output_size"):
            cross_width = int(encoder.hidden_size) * int(getattr(config, "cross_attn_k", 1))
            global_config.encoder_cross_output_size = (
                None if cross_width == int(global_config.hidden_size) else cross_width
            )
    if hasattr(config, "vision_config") and hasattr(config, "merged_hidden_size"):
        merge = int(getattr(config.vision_config, "spatial_merge_size", 1))
        config.merged_hidden_size = int(config.vision_config.hidden_size) * merge * merge
    if getattr(config, "model_type", None) in {"deepseek_v32", "glm_moe_dsa"}:
        config.head_dim = config.qk_rope_head_dim
    if hasattr(config, "kv_lora_rank") and hasattr(config, "qk_rope_head_dim"):
        config.num_key_value_heads = config.num_attention_heads
    if getattr(config, "model_type", None) == "deepseek_v4":
        for rope in config.rope_parameters.values():
            if isinstance(rope, dict):
                rope["partial_rotary_factor"] = 0.5
    if hasattr(config, "use_mamba_kernels"):
        config.use_mamba_kernels = False
    if getattr(config, "model_type", None) == "mamba2":
        config.conv_kernel = 2
    if not hasattr(config, "num_key_value_heads") and hasattr(config, "num_attention_heads"):
        try:
            object.__setattr__(config, "num_key_value_heads", config.num_attention_heads)
        except (AttributeError, TypeError):
            pass
    if getattr(config, "model_type", None) == "hgnet_v2":
        config.stem_channels = [3, 16, 16]
    return config


def _transformers_model(version: ResolvedVersion) -> tuple[nn.Module, dict[str, Any]]:
    from transformers import AutoConfig, AutoModel

    if version.architecture_key == "encoder-decoder":
        from transformers import BertConfig, EncoderDecoderConfig, EncoderDecoderModel

        encoder = _compact_config(BertConfig())
        decoder = _compact_config(BertConfig(is_decoder=True, add_cross_attention=True))
        config = EncoderDecoderConfig.from_encoder_decoder_configs(encoder, decoder)
        config.use_cache = False
        return EncoderDecoderModel(config), config.to_dict()
    if version.architecture_key == "rag":
        from transformers import BartConfig, BertConfig, RagConfig, RagModel

        question = _compact_config(BertConfig())
        generator = _compact_config(BartConfig())
        config = RagConfig.from_question_encoder_generator_configs(question, generator, n_docs=1)
        return RagModel(config), config.to_dict()

    config = AutoConfig.for_model(version.architecture_key)
    _compact_config(config)
    if version.architecture_key == "funnel":
        config.block_sizes = (1,)
        config.block_repeats = [1]
        config.num_decoder_layers = 1
        for name, value in (("bos_token_id", 1), ("eos_token_id", 2), ("pad_token_id", 0)):
            object.__setattr__(config, name, value)
    if version.architecture_key == "reformer":
        config.axial_pos_shape = (4, 8)
        config.axial_pos_embds_dim = (8, 8)
    if version.architecture_key == "rwkv":
        config.num_hidden_layers = 2
    if hasattr(config, "use_timm_backbone"):
        config.use_timm_backbone = False
        if getattr(config, "backbone_config", None) is None:
            from transformers import ResNetConfig

            backbone = _compact_config(ResNetConfig())
            config.backbone_config = backbone
    if version.architecture_key in {"chmv2", "depth_anything"}:
        backbone = config.backbone_config
        backbone.num_hidden_layers = 4
        backbone.stage_names = ["stem", "stage1", "stage2", "stage3", "stage4"]
        backbone.out_indices = [1, 2, 3, 4]
        backbone.out_features = ["stage1", "stage2", "stage3", "stage4"]
    if version.architecture_key == "cvt":
        config.depth = (1, 2, 3)
    if version.architecture_key == "depth_pro":
        config.patch_model_config.num_hidden_layers = 2
        config.intermediate_hook_ids = [0, 1]
    if version.architecture_key == "dbrx" and not hasattr(config.attn_config, "rope_theta"):
        rope_parameters = config.rope_parameters or {"rope_theta": 10000.0}
        object.__setattr__(config.attn_config, "rope_theta", rope_parameters.get("rope_theta", 10000.0))
    if version.architecture_key == "dbrx" and config.attn_config.clip_qkv is None:
        object.__setattr__(config.attn_config, "clip_qkv", 1e6)
    if version.architecture_key == "dbrx":
        config.ffn_config.hidden_size = config.d_model
        config.ffn_config.ffn_hidden_size = config.d_model
    try:
        module = __import__(version.entrypoint_module, fromlist=[version.entrypoint_class])
        model_class = getattr(module, version.entrypoint_class)
    except (ImportError, AttributeError):
        model = AutoModel.from_config(config)
    else:
        model = model_class(config)
    if version.architecture_key == "xmod" and hasattr(model, "set_default_language"):
        model.set_default_language(config.languages[0])
    return model, config.to_dict()


def _required_constructor_value(name: str) -> Any:
    values = {
        "sample_size": 16,
        "in_channels": 3,
        "out_channels": 3,
        "down_block_types": ("DownBlock2D",),
        "up_block_types": ("UpBlock2D",),
        "block_out_channels": (16,),
        "layers_per_block": 1,
        "cross_attention_dim": 16,
        "attention_head_dim": 4,
        "num_attention_heads": 4,
        "patch_size": 2,
        "num_layers": 1,
        "num_vector_embeds": 64,
        "latent_channels": 4,
        "norm_num_groups": 4,
    }
    if name in values:
        return values[name]
    if name.endswith("_dim") or name.endswith("_size") or name.startswith("num_"):
        return 4
    if name.endswith("_channels"):
        return 3
    raise TypeError(f"no compact constructor value for required parameter {name!r}")


def _diffusers_model(version: ResolvedVersion) -> tuple[nn.Module, dict[str, Any]]:
    import diffusers

    model_class = getattr(diffusers, version.entrypoint_class)
    signature = inspect.signature(model_class.__init__)
    kwargs: dict[str, Any] = {}
    for name, parameter in signature.parameters.items():
        if name == "self" or parameter.kind in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD):
            continue
        if name in {"down_block_types", "up_block_types"} and isinstance(parameter.default, tuple):
            kwargs[name] = parameter.default[:1]
        elif name == "block_out_channels" and isinstance(parameter.default, tuple):
            kwargs[name] = (16,)
        elif name in COMPACT_VALUES:
            value = COMPACT_VALUES[name]
            if isinstance(parameter.default, tuple):
                value = tuple(value for _ in parameter.default)
            elif isinstance(parameter.default, list):
                value = [value for _ in parameter.default]
            kwargs[name] = value
        elif parameter.default is inspect.Parameter.empty:
            kwargs[name] = _required_constructor_value(name)
    model = model_class(**kwargs)
    config = dict(getattr(model, "config", kwargs))
    return model, config


def _tensor_for_parameter(name: str, model: nn.Module, config: dict[str, Any]) -> torch.Tensor:
    batch, sequence = 1, 4
    if name in {"input_ids", "decoder_input_ids", "labels"} or name.endswith("_ids"):
        return torch.zeros((batch, sequence), dtype=torch.long)
    if name in {"attention_mask", "decoder_attention_mask", "token_type_ids"} or name.endswith("_mask"):
        return torch.ones((batch, sequence), dtype=torch.long)
    if name in {"pixel_values", "images", "image"}:
        return torch.zeros((batch, 3, 16, 16), dtype=torch.float32)
    if "input_features" in name or "audio" in name:
        return torch.zeros((batch, 16, 16), dtype=torch.float32)
    if name in {"input_values", "waveform"}:
        return torch.zeros((batch, 64), dtype=torch.float32)
    if name in {"sample", "hidden_states", "encoder_hidden_states"}:
        channels = int(config.get("in_channels", config.get("latent_channels", 3)))
        if "1D" in type(model).__name__:
            return torch.zeros((batch, channels, 16), dtype=torch.float32)
        if "3D" in type(model).__name__ or "Video" in type(model).__name__:
            return torch.zeros((batch, channels, 2, 8, 8), dtype=torch.float32)
        if name == "encoder_hidden_states":
            width = int(config.get("cross_attention_dim", config.get("hidden_size", 16)))
            if isinstance(width, (tuple, list)):
                width = int(width[0])
            return torch.zeros((batch, sequence, width), dtype=torch.float32)
        return torch.zeros((batch, channels, 16, 16), dtype=torch.float32)
    return torch.zeros((batch, sequence, int(config.get("hidden_size", 16))), dtype=torch.float32)


def _representative_inputs(model: nn.Module, config: dict[str, Any]) -> tuple[tuple[Any, ...], dict[str, Any]]:
    signature = inspect.signature(model.forward)
    parameter_names = set(signature.parameters)
    dummy = getattr(model, "dummy_inputs", None)
    generic_text_only = not config.get("is_encoder_decoder") and "input_ids" in parameter_names and not parameter_names.intersection({
        "pixel_values", "input_features", "input_values", "states", "sample", "hidden_states"
    })
    if generic_text_only and isinstance(dummy, dict) and dummy and set(dummy).issubset(parameter_names):
        return (), {key: value.cpu() if torch.is_tensor(value) else value for key, value in dummy.items()}

    kwargs: dict[str, Any] = {}
    if "timestep" in parameter_names:
        kwargs["timestep"] = torch.ones((1,), dtype=torch.long)
    elif "timesteps" in parameter_names:
        kwargs["timesteps"] = torch.ones((1,), dtype=torch.long)
    if "states" in parameter_names:
        batch, sequence = 1, 4
        kwargs.update({
            "states": torch.zeros((batch, sequence, int(config.get("state_dim", 4)))),
            "actions": torch.zeros((batch, sequence, int(config.get("act_dim", 2)))),
            "rewards": torch.zeros((batch, sequence, 1)),
            "returns_to_go": torch.zeros((batch, sequence, 1)),
            "timesteps": torch.zeros((batch, sequence), dtype=torch.long),
            "attention_mask": torch.ones((batch, sequence), dtype=torch.long),
        })
    else:
        if "input_ids" in parameter_names:
            kwargs["input_ids"] = torch.zeros((1, 4), dtype=torch.long)
        if "pixel_values" in parameter_names:
            model_type = getattr(model.config, "model_type", "")
            image_extent = 32 if model_type in {
                "convnext", "convnextv2", "cvt", "depth_pro", "d_fine", "deimv2",
                "efficientnet", "glpn", "mobilevit", "mobilevitv2", "pvt", "pvt_v2",
                "rt_detr", "rt_detr_v2", "segformer", "swin", "swinv2", "textnet",
            } else 16
            kwargs["pixel_values"] = torch.zeros((1, 3, image_extent, image_extent))
            if model_type in {"efficientloftr", "lightglue"}:
                kwargs["pixel_values"] = torch.zeros((1, 2, 3, image_extent, image_extent))
        if "image_grid_thw" in parameter_names:
            model_type = getattr(model.config, "model_type", "")
            if model_type == "glm_image":
                kwargs["image_grid_thw"] = torch.tensor([[1, 1, 1], [1, 1, 1]], dtype=torch.long)
                kwargs["images_per_sample"] = torch.tensor([2], dtype=torch.long)
                vision = config.get("vision_config", {})
                patch_size = int(vision.get("patch_size", 4))
                kwargs["pixel_values"] = torch.zeros((1, 3 * patch_size * patch_size))
                kwargs["input_ids"] = torch.tensor([[
                    model.config.image_start_token_id,
                    model.config.image_token_id,
                    model.config.image_end_token_id,
                ]])
            else:
                vision = config.get("vision_config", {})
                patch_size = int(vision.get("patch_size", 4))
                grid_size = 2
                kwargs["image_grid_thw"] = torch.tensor([[1, grid_size, grid_size]], dtype=torch.long)
                merge = int(vision.get("spatial_merge_size", 1))
                token_count = max(1, grid_size * grid_size // (merge * merge))
                temporal = int(vision.get("temporal_patch_size", 1))
                channels = int(vision.get("in_channels", 3))
                kwargs["pixel_values"] = torch.zeros((
                    grid_size * grid_size, channels * temporal * patch_size * patch_size
                ))
                kwargs["input_ids"] = torch.full(
                    (1, token_count), int(getattr(model.config, "image_token_id", 1)), dtype=torch.long
                )
        if "input_features" in parameter_names:
            model_type = getattr(model.config, "model_type", "")
            feature_size = int(config.get(
                "feature_projection_input_dim",
                config.get("input_feat_per_channel", config.get("num_mel_bins", config.get("feature_size", 16))),
            ))
            frames = max(64, int(config.get("max_source_positions", 32)) * 2)
            if model_type == "whisper":
                kwargs["input_features"] = torch.zeros((1, feature_size, frames))
            else:
                kwargs["input_features"] = torch.zeros((1, frames, feature_size))
        if "input_values" in parameter_names:
            if getattr(model.config, "model_type", "") == "audio-spectrogram-transformer":
                kwargs["input_values"] = torch.zeros((1, 64, int(config.get("num_mel_bins", 16))))
            else:
                kwargs["input_values"] = torch.zeros((1, 4096))
        if "decoder_input_ids" in parameter_names and (
            "input_features" in kwargs or "pixel_values" in kwargs or "input_values" in kwargs
            or config.get("is_encoder_decoder")
        ):
            kwargs["decoder_input_ids"] = torch.zeros((1, 4), dtype=torch.long)
        if getattr(model.config, "model_type", "") == "deepseek_ocr2":
            kwargs["input_ids"] = torch.full(
                (1, 145), int(model.config.image_token_id), dtype=torch.long
            )
        if getattr(model.config, "model_type", "") == "modernvbert":
            kwargs["pixel_values"] = torch.zeros((1, 1, 3, 16, 16))
            kwargs["input_ids"] = torch.tensor([[int(model.config.image_token_id)]])
        if getattr(model.config, "model_type", "") == "clap" and "input_features" in kwargs:
            kwargs["input_features"] = kwargs["input_features"].unsqueeze(1)
        if getattr(model.config, "model_type", "") == "t5gemma2":
            kwargs["input_ids"] = torch.full(
                (1, int(model.config.encoder.mm_tokens_per_image)),
                int(model.config.image_token_index),
                dtype=torch.long,
            )
        if "mm_token_type_ids" in parameter_names and "input_ids" in kwargs:
            kwargs["mm_token_type_ids"] = torch.ones_like(kwargs["input_ids"], dtype=torch.int)
        if getattr(model.config, "model_type", "") == "rag":
            kwargs.update({
                "input_ids": torch.zeros((1, 4), dtype=torch.long),
                "context_input_ids": torch.zeros((1, 4), dtype=torch.long),
                "context_attention_mask": torch.ones((1, 4), dtype=torch.long),
                "doc_scores": torch.ones((1, 1)),
            })
    for name, parameter in signature.parameters.items():
        if name == "self" or parameter.kind in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD):
            continue
        if name in kwargs or parameter.default is not inspect.Parameter.empty:
            continue
        if name in {"timestep", "timesteps"}:
            kwargs[name] = torch.tensor(1)
        elif name in {"return_dict"}:
            kwargs[name] = True
        else:
            kwargs[name] = _tensor_for_parameter(name, model, config)
    if not kwargs:
        kwargs["input_ids"] = torch.zeros((1, 4), dtype=torch.long)
    if "class_labels" in parameter_names and "class_labels" not in kwargs:
        kwargs["class_labels"] = torch.zeros((1,), dtype=torch.long)
    return (), kwargs


def create_model(version: ResolvedVersion) -> ModelBundle:
    if version.library == "transformers":
        model, config = _transformers_model(version)
    else:
        model, config = _diffusers_model(version)
    model.cpu().eval()
    inputs, kwargs = _representative_inputs(model, config)
    return ModelBundle(model, inputs, kwargs, config)
