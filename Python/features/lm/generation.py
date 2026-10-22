"""Desktop generation orchestration over captured inputs and an owned session."""
from dataclasses import dataclass
from typing import Any, Callable

from .domain import build_request
from .project_tools import ProjectTools, TOOLS


@dataclass(frozen=True)
class GenerationInputs:
    profile: dict
    project: Any = None
    buffers: Any = None


@dataclass(frozen=True)
class PreparedGeneration:
    profile: dict
    payload: dict
    metadata: dict
    project_tools: Any = None


@dataclass(frozen=True)
class GenerationResult:
    started: bool
    error: str = ''
    save_error: Exception | None = None


class GenerationCoordinator:
    def __init__(self, session, client):
        self.session, self.client = session, client

    def prepare(self, inputs: GenerationInputs) -> PreparedGeneration:
        data = self.session.data
        project, tools = inputs.project, None
        if data.get('mode') == 'code':
            if project is None:
                raise ValueError('Choose a registered IDE project. Register one in IDE, then refresh projects.')
            tools = ProjectTools(project, inputs.buffers)
        payload, metadata = build_request(data, tools=TOOLS if tools else None,
                                         project_name=tools.name if tools else None)
        if tools:
            metadata.update(project_id=project.id, project_name=project.name, project_root=str(project.root))
        metadata['base_url'] = inputs.profile['base_url']
        return PreparedGeneration(dict(inputs.profile), payload, metadata, tools)

    def start(self, plan: PreparedGeneration, token: str, *, clear_draft: bool,
              published: Callable[[], None]) -> GenerationResult:
        """Publication failures propagate before UI clearing or transport dispatch.

        The callback updates presentation after durable publication. Credentials
        are supplied only for dispatch and are never retained on this coordinator.
        """
        self.session.begin_response(plan.metadata, clear_draft=clear_draft)
        published()
        try:
            if plan.project_tools:
                self.client.start(plan.profile, token, plan.payload, project_tools=plan.project_tools,
                                  context_tokens=self.session.data['settings']['context_tokens'])
            else:
                self.client.start(plan.profile, token, plan.payload)
        except (ValueError, OSError) as error:
            self.session.complete_response('failed', str(error), {})
            save_error = None
            try:
                self.session.save()
            except (OSError, ValueError, UnicodeError) as failure:
                save_error = failure
            return GenerationResult(False, str(error), save_error)
        return GenerationResult(True)
