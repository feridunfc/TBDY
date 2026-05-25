from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass


class EvaluationDAGError(Exception):
    """Raised when evaluation dependency metadata cannot form a valid DAG."""


@dataclass(frozen=True)
class EvaluationNode:
    evaluation: str
    depends_on: tuple[str, ...]
    enabled: bool
    experimental: bool


@dataclass(frozen=True)
class EvaluationDAG:
    nodes: tuple[EvaluationNode, ...]

    @classmethod
    def from_catalog(cls, catalog: object, *, enabled_only: bool = False) -> "EvaluationDAG":
        evaluations_obj = _member(catalog, "evaluations")
        raw_nodes = []

        for evaluation_name, evaluation_obj in _iter_named_objects(evaluations_obj):
            enabled = _bool_member(evaluation_obj, "enabled", default=True)
            if enabled_only and not enabled:
                continue
            raw_nodes.append(
                EvaluationNode(
                    evaluation=evaluation_name,
                    depends_on=_depends_on_results(evaluation_obj),
                    enabled=enabled,
                    experimental=_bool_member(evaluation_obj, "experimental", default=False),
                )
            )

        included_names = {node.evaluation for node in raw_nodes}
        nodes = tuple(
            sorted(
                (
                    EvaluationNode(
                        evaluation=node.evaluation,
                        depends_on=tuple(dep for dep in node.depends_on if dep in included_names),
                        enabled=node.enabled,
                        experimental=node.experimental,
                    )
                    if enabled_only
                    else node
                )
                for node in raw_nodes
            , key=lambda node: node.evaluation)
        )
        return cls(nodes=nodes)

    @property
    def evaluations(self) -> tuple[str, ...]:
        return tuple(node.evaluation for node in self.nodes)

    @property
    def enabled_evaluations(self) -> tuple[str, ...]:
        return tuple(node.evaluation for node in self.nodes if node.enabled)

    def to_dict(self) -> dict[str, object]:
        return {
            "nodes": [
                {
                    "evaluation": node.evaluation,
                    "depends_on": list(node.depends_on),
                    "enabled": node.enabled,
                    "experimental": node.experimental,
                }
                for node in self.nodes
            ],
            "topological_order": list(self.topological_order()),
        }

    def topological_order(self, enabled_only: bool = True) -> tuple[str, ...]:
        node_by_name = {node.evaluation: node for node in self.nodes}
        selected_names = {
            node.evaluation for node in self.nodes if not enabled_only or node.enabled
        }
        ordered_names = sorted(selected_names)
        permanent: set[str] = set()
        temporary: set[str] = set()
        result: list[str] = []

        def visit(evaluation: str, path: tuple[str, ...]) -> None:
            if evaluation in permanent:
                return
            if evaluation in temporary:
                cycle = " -> ".join(path + (evaluation,))
                raise EvaluationDAGError(f"Cycle detected in evaluation dependencies: {cycle}")

            node = node_by_name[evaluation]
            temporary.add(evaluation)
            for dependency in sorted(node.depends_on):
                if dependency not in node_by_name:
                    raise EvaluationDAGError(
                        f"Evaluation '{evaluation}' depends on unknown evaluation '{dependency}'."
                    )
                dependency_node = node_by_name[dependency]
                if enabled_only and not dependency_node.enabled:
                    continue
                if dependency not in selected_names:
                    continue
                visit(dependency, path + (evaluation,))
            temporary.remove(evaluation)
            permanent.add(evaluation)
            result.append(evaluation)

        for evaluation in ordered_names:
            visit(evaluation, ())

        return tuple(result)


def _member(obj: object, name: str) -> object:
    if isinstance(obj, Mapping):
        return obj.get(name)
    return getattr(obj, name, None)


def _bool_member(obj: object, name: str, *, default: bool) -> bool:
    value = _member(obj, name)
    if value is None:
        return default
    return bool(value)


def _iter_named_objects(obj: object) -> tuple[tuple[str, object], ...]:
    if isinstance(obj, Mapping):
        return tuple((str(key), value) for key, value in obj.items())
    if isinstance(obj, Sequence) and not isinstance(obj, (str, bytes, bytearray)):
        return tuple((str(index), value) for index, value in enumerate(obj))
    return ()


def _string_sequence(value: object) -> tuple[str, ...]:
    if value in (None, ""):
        return ()
    if isinstance(value, str):
        return (value,) if value else ()
    if isinstance(value, Sequence):
        return tuple(str(item) for item in value if str(item))
    return ()


def _depends_on_results(evaluation_obj: object) -> tuple[str, ...]:
    explicit = _string_sequence(_member(evaluation_obj, "depends_on_results"))
    if explicit:
        return tuple(sorted(dict.fromkeys(explicit)))
    return ()
