"""Portable SSE framing for OpenAI-compatible responses."""

import json
from .domain import MAX_TEXT
from commonUtils.runtime.streams.sse import SSEDataDecoder, SSERecordLimit


class StreamDecoder:
    """SSE framing accepts arbitrary UTF-8/network boundaries and CRLF lines."""

    def __init__(self, *, allow_tools=False, max_choices=None):
        self.allow_tools = allow_tools
        self.max_choices = max_choices
        self.tool_calls = {}
        self.events = SSEDataDecoder(max_record=2 * 1024 * 1024)
        self.done = False
        self.finished = False
        self.finish_reason = None
        self.usage = None
        self.text = ""

    def feed(self, chunk):
        try:
            return self._feed_events(chunk)
        except SSERecordLimit:
            raise ValueError("Server stream record exceeds the size limit.") from None

    def _feed_events(self, chunk):
        fragments = []
        for value in self.events.feed(chunk):
            if value == "[DONE]":
                self.done = True
                continue
            if self.done:
                raise ValueError("Server sent data after the end of the response.")
            event = json.loads(value)
            if not isinstance(event, dict) or "error" in event:
                raise ValueError(
                    "Server returned an invalid response or generation error."
                )
            if isinstance(event.get("usage"), dict):
                self.usage = event["usage"]
            choices = event.get("choices", [])
            if not isinstance(choices, list):
                raise ValueError("Invalid response choices.")
            if self.max_choices is not None and len(choices) > self.max_choices:
                raise ValueError("Only one text response is supported.")
            if not choices:
                continue
            choice = choices[0]
            if not isinstance(choice, dict):
                raise ValueError("Invalid response choice.")
            delta = choice.get("delta", {})
            if not isinstance(delta, dict):
                raise ValueError("Invalid response delta.")
            if (
                delta.get("tool_calls")
                or delta.get("function_call")
                or choice.get("finish_reason") in ("tool_calls", "function_call")
            ):
                if not self.allow_tools:
                    raise ValueError("This chat client does not execute model tools.")
                for fragment in delta.get("tool_calls", []):
                    index = fragment["index"]
                    if type(index) is not int or not 0 <= index < 8:
                        raise ValueError("Invalid tool index.")
                    call = self.tool_calls.setdefault(
                        index,
                        dict(
                            id="", type="function", function=dict(name="", arguments="")
                        ),
                    )
                    for key in ("id", "type"):
                        if key in fragment:
                            call[key] = fragment[key]
                    for key in ("name", "arguments"):
                        value = fragment.get("function", {}).get(key, "")
                        if not isinstance(value, str):
                            raise ValueError("Invalid tool fragment.")
                        call["function"][key] += value
                        if len(call["function"][key]) > 65536:
                            raise ValueError("Tool call exceeds size limit.")
            text = delta.get("content") or ""
            if not isinstance(text, str):
                raise ValueError("Only text responses are supported.")
            if len(self.text) + len(text) > MAX_TEXT:
                raise ValueError("Response exceeds the text size limit.")
            self.text += text
            fragments.append(text)
            if choice.get("finish_reason") is not None:
                self.finished = True
                self.finish_reason = choice["finish_reason"]
        return "".join(fragments)
