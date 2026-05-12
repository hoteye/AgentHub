from __future__ import annotations

from typing import Any, Callable, Mapping

from .models import McpPromptDescriptor, McpResourceDescriptor

MappingFn = Callable[[Any], dict[str, Any]]


def prompt_descriptors(
    *,
    server_name: str,
    config: Mapping[str, Any],
    session: Any,
    remote_entries: list[dict[str, Any]] | None = None,
    mapping_fn: MappingFn,
) -> list[McpPromptDescriptor]:
    remote = (
        prompt_descriptors_from_entries(server_name=server_name, entries=remote_entries, mapping_fn=mapping_fn)
        if isinstance(remote_entries, list)
        else _remote_prompt_descriptors(server_name=server_name, session=session, mapping_fn=mapping_fn)
    )
    if remote:
        return remote
    return _config_prompt_descriptors(server_name=server_name, config=config, mapping_fn=mapping_fn)


def resource_descriptors(
    *,
    server_name: str,
    config: Mapping[str, Any],
    session: Any,
    remote_entries: list[dict[str, Any]] | None = None,
    mapping_fn: MappingFn,
) -> list[McpResourceDescriptor]:
    remote = (
        resource_descriptors_from_entries(server_name=server_name, entries=remote_entries, mapping_fn=mapping_fn)
        if isinstance(remote_entries, list)
        else _remote_resource_descriptors(server_name=server_name, session=session, mapping_fn=mapping_fn)
    )
    if remote:
        return remote
    return _config_resource_descriptors(server_name=server_name, config=config, mapping_fn=mapping_fn)


def read_remote_resource(
    *,
    session: Any,
    server_name: str,
    uri: str,
) -> dict[str, Any] | None:
    resources_read = getattr(session, "resources_read", None)
    if not callable(resources_read):
        return None
    target_uri = str(uri or "").strip()
    if not target_uri:
        return {"ok": False, "error": "uri is required", "server_name": server_name, "uri": target_uri}
    try:
        raw_result = resources_read(uri=target_uri)
    except Exception as exc:
        return {
            "ok": False,
            "error": f"resource read failed: {exc}",
            "server_name": server_name,
            "uri": target_uri,
        }
    if not isinstance(raw_result, Mapping):
        return {"ok": False, "error": "invalid resource payload", "server_name": server_name, "uri": target_uri}
    result = dict(raw_result)
    if bool(result.get("error")) and "contents" not in result:
        return {
            "ok": False,
            "error": str(result.get("error") or "resource read failed"),
            "server_name": server_name,
            "uri": target_uri,
        }
    contents = _contents_from_read_result(result, target_uri)
    mime_type = _mime_type_from_read_result(result, contents)
    return {
        "ok": True,
        "server_name": server_name,
        "uri": target_uri,
        "name": str(result.get("name") or "").strip(),
        "mime_type": mime_type,
        "description": str(result.get("description") or "").strip(),
        "contents": contents,
        "text": result.get("text"),
        "blob": result.get("blob"),
    }


def _remote_prompt_descriptors(
    *,
    server_name: str,
    session: Any,
    mapping_fn: MappingFn,
) -> list[McpPromptDescriptor]:
    prompts_list = getattr(session, "prompts_list", None)
    if not callable(prompts_list):
        return []
    try:
        raw = prompts_list()
    except Exception:
        return []
    if not isinstance(raw, list):
        return []
    return prompt_descriptors_from_entries(
        server_name=server_name,
        entries=[dict(item) for item in raw if isinstance(item, Mapping)],
        mapping_fn=mapping_fn,
    )


def _config_prompt_descriptors(
    *,
    server_name: str,
    config: Mapping[str, Any],
    mapping_fn: MappingFn,
) -> list[McpPromptDescriptor]:
    prompts: list[McpPromptDescriptor] = []
    raw = config.get("prompts") or config.get("prompt_descriptors") or []
    if isinstance(raw, Mapping):
        raw = [{**(value if isinstance(value, dict) else {}), "name": name} for name, value in raw.items()]
    if not isinstance(raw, list):
        return prompts
    for entry in raw:
        if not isinstance(entry, Mapping):
            continue
        name = str(entry.get("name") or "").strip()
        if not name:
            continue
        arguments = entry.get("arguments")
        if not isinstance(arguments, list):
            arguments = []
        prompts.append(
            McpPromptDescriptor(
                server_name=server_name,
                name=name,
                title=str(entry.get("title") or "").strip(),
                description=str(entry.get("description") or "").strip(),
                arguments=[dict(arg) for arg in arguments if isinstance(arg, Mapping)],
                metadata=mapping_fn(entry.get("metadata")),
            )
        )
    return prompts


def _remote_resource_descriptors(
    *,
    server_name: str,
    session: Any,
    mapping_fn: MappingFn,
) -> list[McpResourceDescriptor]:
    resources_list = getattr(session, "resources_list", None)
    if not callable(resources_list):
        return []
    try:
        raw = resources_list()
    except Exception:
        return []
    if not isinstance(raw, list):
        return []
    return resource_descriptors_from_entries(
        server_name=server_name,
        entries=[dict(item) for item in raw if isinstance(item, Mapping)],
        mapping_fn=mapping_fn,
    )


def prompt_descriptors_from_entries(
    *,
    server_name: str,
    entries: list[dict[str, Any]] | None,
    mapping_fn: MappingFn,
) -> list[McpPromptDescriptor]:
    prompts: list[McpPromptDescriptor] = []
    for entry in entries or []:
        if not isinstance(entry, Mapping):
            continue
        name = str(entry.get("name") or "").strip()
        if not name:
            continue
        arguments = entry.get("arguments")
        if not isinstance(arguments, list):
            arguments = []
        prompts.append(
            McpPromptDescriptor(
                server_name=server_name,
                name=name,
                title=str(entry.get("title") or "").strip(),
                description=str(entry.get("description") or "").strip(),
                arguments=[dict(item) for item in arguments if isinstance(item, Mapping)],
                metadata=mapping_fn(entry.get("metadata")),
            )
        )
    return prompts


def resource_descriptors_from_entries(
    *,
    server_name: str,
    entries: list[dict[str, Any]] | None,
    mapping_fn: MappingFn,
) -> list[McpResourceDescriptor]:
    resources: list[McpResourceDescriptor] = []
    for entry in entries or []:
        if not isinstance(entry, Mapping):
            continue
        uri = str(entry.get("uri") or "").strip()
        if not uri:
            continue
        resources.append(
            McpResourceDescriptor(
                server_name=server_name,
                uri=uri,
                name=str(entry.get("name") or "").strip(),
                title=str(entry.get("title") or "").strip(),
                description=str(entry.get("description") or "").strip(),
                mime_type=str(entry.get("mime_type") or entry.get("mimeType") or "").strip(),
                metadata=mapping_fn(entry.get("metadata")),
            )
        )
    return resources


def _config_resource_descriptors(
    *,
    server_name: str,
    config: Mapping[str, Any],
    mapping_fn: MappingFn,
) -> list[McpResourceDescriptor]:
    resources: list[McpResourceDescriptor] = []
    raw = config.get("resources") or config.get("resource_descriptors") or []
    if isinstance(raw, Mapping):
        raw = [{**(value if isinstance(value, dict) else {}), "uri": uri} for uri, value in raw.items()]
    if not isinstance(raw, list):
        return resources
    for entry in raw:
        if not isinstance(entry, Mapping):
            continue
        uri = str(entry.get("uri") or "").strip()
        if not uri:
            continue
        resources.append(
            McpResourceDescriptor(
                server_name=server_name,
                uri=uri,
                name=str(entry.get("name") or "").strip(),
                title=str(entry.get("title") or "").strip(),
                description=str(entry.get("description") or "").strip(),
                mime_type=str(entry.get("mime_type") or entry.get("mimeType") or "").strip(),
                metadata=mapping_fn(entry.get("metadata")),
            )
        )
    return resources


def _contents_from_read_result(result: Mapping[str, Any], uri: str) -> list[dict[str, Any]]:
    raw_contents = result.get("contents")
    if isinstance(raw_contents, list):
        return [dict(item) for item in raw_contents if isinstance(item, Mapping)]
    inline: dict[str, Any] = {"uri": uri}
    mime_type = str(result.get("mime_type") or result.get("mimeType") or "").strip()
    if mime_type:
        inline["mimeType"] = mime_type
    if result.get("text") is not None:
        inline["text"] = result.get("text")
    if result.get("blob") is not None:
        inline["blob"] = result.get("blob")
    if len(inline) > 1:
        return [inline]
    return []


def _mime_type_from_read_result(result: Mapping[str, Any], contents: list[dict[str, Any]]) -> str:
    mime_type = str(result.get("mime_type") or result.get("mimeType") or "").strip()
    if mime_type:
        return mime_type
    for item in contents:
        candidate = str(item.get("mime_type") or item.get("mimeType") or "").strip()
        if candidate:
            return candidate
    return ""
