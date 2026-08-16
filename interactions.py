from enum import IntEnum
from typing import Dict, Any, List

__all__ = ["InteractionFlag", "build_string_response", "TextComponent", "ThumbnailComponent",
           "SectionComponent", "ContainerComponent", "build_component_response"]


class InteractionType(IntEnum):
    CHANNEL_MESSAGE_WITH_SOURCE = 4


class InteractionFlag(IntEnum):
    SUPPRESS_EMBEDS = 1 << 2
    EPHEMERAL = 1 << 6
    IS_COMPONENTS_V2 = 1 << 15


class ComponentType(IntEnum):
    SECTION = 9
    TEXT_DISPLAY = 10
    THUMBNAIL = 11
    CONTAINER = 17


class Component:
    type: ComponentType
    props: Dict[str, Any]

    def __init__(self, type: ComponentType, **kwargs):
        self.type = type
        self.props = kwargs

    def render(self) -> Dict[str, Any]:
        rendered: Dict[str, Any] = {}

        for k, v in self.props.items():
            if v is not None:
                rendered[k] = _render(v)
        rendered["type"] = self.type.value
        return rendered


def _render(object: Any) -> Any:
    if isinstance(object, Component):
        return object.render()
    elif isinstance(object, list):
        return [_render(item) for item in object]
    elif isinstance(object, dict):
        return {k: _render(v) for k, v in object.items()}
    else:
        return object


class TextComponent(Component):
    def __init__(self, content: str):
        super().__init__(ComponentType.TEXT_DISPLAY, content=content)


class ThumbnailComponent(Component):
    def __init__(self, url: str):
        super().__init__(ComponentType.THUMBNAIL, media={"url": url})


class ContainerComponent(Component):
    def __init__(self, components: List[Component], accent_color: int | None = None):
        super().__init__(ComponentType.CONTAINER,
                         components=components,
                         accent_color=accent_color)


class SectionComponent(Component):
    def __init__(self, components: List[Component], accessory: Component | None = None):
        super().__init__(ComponentType.SECTION, components=components, accessory=accessory)


def build_string_response(message: str, flags: int = 0) -> Dict[str, Any]:
    return {"type": InteractionType.CHANNEL_MESSAGE_WITH_SOURCE,
            "data": {"content": message,
                     "flags": flags}}


def build_component_response(components: List[Component], flags: int = 0) -> Dict[str, Any]:
    return {"type": InteractionType.CHANNEL_MESSAGE_WITH_SOURCE,
            "data": {"flags": flags,
                     "components": [c.render() for c in components]}}
