__all__ = [
    "get_embeddings",
    "one_chat",
    "multi_chat"
]

import os
import typing
from openai import OpenAI
from openai.types.chat import ChatCompletionUserMessageParam, ChatCompletionAssistantMessageParam

# Config
LLM_SP_AK = os.getenv("LLM_SP_AK", "")
LLM_SP_BASE_URL = os.getenv("LLM_SP_BASE_URL", "")

OPENAI_CLIENT = OpenAI(
    base_url=LLM_SP_BASE_URL,
    api_key=LLM_SP_AK,
)


def get_embeddings(
    text: str,
    model: str = "baai/bge-m3",
    encoding_format: typing.Literal['float', 'base64'] = "float",
):
    response = OPENAI_CLIENT.embeddings.create(
        model=model,
        input=text,
        encoding_format=encoding_format
    )
    return response.data[0].embedding


def one_chat(
    prompt: str | None = None,
    model: str = "deepseek/deepseek-v3-0324",
    history_messages: list[ChatCompletionUserMessageParam | ChatCompletionAssistantMessageParam] | None = None,
):
    chat_completion_res = OPENAI_CLIENT.chat.completions.create(
        model=model,
        messages=[
            ChatCompletionUserMessageParam(
                role="user",
                content=prompt,
            ),
            *(history_messages or [])
        ],
        stream=False,
    )
    return chat_completion_res.choices[0].message.content

def multi_chat(
    init_prompt: str | None = None,
    model: str = "deepseek/deepseek-v3-0324"
) -> typing.Callable[[str], str]:
    messages = []

    def wrapper(prompt: str) -> str:
        nonlocal messages

        if not messages:
            prompt = init_prompt + prompt
        messages.append(ChatCompletionUserMessageParam(
            role="user",
            content=prompt,
        ))
        response = one_chat(prompt=prompt, model=model, history_messages=messages)
        messages.append(ChatCompletionAssistantMessageParam(
            role="assistant",
            content=response,
        ))
        return response

    return wrapper
