import enum
import pydantic


enum_serializer = pydantic.PlainSerializer(
    lambda value: value.value if isinstance(value, enum.Enum) else value,
    return_type=str,
)