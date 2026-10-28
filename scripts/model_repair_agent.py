"""Run one bounded end-to-end repair attempt on an allowlisted evaluation case."""

import argparse
import re
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evaluation.materialize import load_case, materialize_case
from tracerepair.code_retrieval import (
    BailianEmbeddingProvider,
    CodeIndex,
    CodeRagRetriever,
    HashEmbeddingProvider,
    RetrievalError,
)
from tracerepair.instrumented_tools import InstrumentedTools
from tracerepair.function_calling import NativeFunctionPlanner
from tracerepair.langgraph_end_to_end import LangGraphEndToEndRepairWorkflow
from tracerepair.model_planner import BailianChatTransport, PlannerConfig, PlannerError
from tracerepair.models import Task, TaskStatus
from tracerepair.patch_apply import PatchApplier
from tracerepair.patch_policy import PatchPolicy
from tracerepair.read_tools import ReadOnlyRepository
from tracerepair.recovery import (
    PATCH_APPLIED,
    SOURCE_READ,
    TARGET_PASSED,
    InjectedCrash,
    recovery_state,
)
from tracerepair.repository_task import (
    RepositoryTaskError,
    RepositoryTaskSpec,
    materialize_repository,
    runtime_spec,
)
from tracerepair.store import TraceStore
from tracerepair.test_runner import RestrictedTestRunner
from tracerepair.version import (
    AGENT_VERSION,
    MAX_COMPLETION_TOKENS,
    MAX_DIAGNOSIS_TURNS,
    MAX_MODEL_CALLS,
    MAX_TOTAL_COMPLETION_TOKENS,
    MODEL_ID,
    PLANNER_PROTOCOL,
    PROJECT_VERSION,
)
from tracerepair.workflow import case_selector


DEVELOPMENT_CASES = ("01", "03", "05", "07", "10")
LOCKED_CASES = ("02", "04", "06", "08", "09")
DIAGNOSTIC_QUERIES = {
    "01": ("def seen",),
    "02": ("def parse_event",),
    "03": ("def retry",),
    "04": ("def is_retryable_status",),
    "05": ("def read_bool",),
    "06": ("def parse_event",),
    "07": ("def list_after",),
    "08": ("def handle",),
    "09": ("def expired_event_ids",),
    "10": ("def handle_batch",),
}


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--case", choices=DEVELOPMENT_CASES + LOCKED_CASES)
    mode.add_argument(
        "--task",
        type=Path,
        metavar="TASK_JSON",
        help="repair a trusted small Python repository described by a bounded task config",
    )
    mode.add_argument("--resume", metavar="TASK_ID")
    parser.add_argument(
        "--evaluation-split",
        choices=("development", "locked"),
        default="development",
        help="locked cases must be invoked explicitly by the blind-evaluation runner",
    )
    parser.add_argument(
        "--inject-crash-after",
        choices=(SOURCE_READ, PATCH_APPLIED),
        help="test-only fault injection immediately after a durable checkpoint",
    )
    parser.add_argument(
        "--rag",
        choices=("none", "fts", "hash", "hybrid"),
        default="none",
        help="optional code retrieval; hash is an offline vector-path baseline",
    )
    parser.add_argument("--embedding-model", default="qwen3.7-text-embedding-flash")
    parser.add_argument(
        "--embedding-dimensions",
        type=int,
        choices=(256, 512, 768, 1024),
        default=256,
    )
    parser.add_argument("--rag-limit", type=int, choices=range(1, 11), default=5)
    parser.add_argument("--rrf-k", type=int, choices=range(1, 1001), default=60)
    arguments = parser.parse_args()
    store = TraceStore(ROOT / "data" / "model-agent.sqlite3")
    code_index: CodeIndex | None = None
    try:
        if arguments.resume:
            task_id = arguments.resume
            task = _prepare_resume(store, task_id, parser)
            issue = task.issue
            workspace = Path(task.workspace).resolve()
            checkpoint = store.load_checkpoint(task_id)
            configured = checkpoint.get("repository_task")
            if isinstance(configured, dict):
                spec = runtime_spec(configured, workspace, issue)
                case_id = task.case_id
                case_name = spec.name
                selector = spec.target_test
                diagnostic_queries = spec.diagnostic_queries
                source_allowlist = spec.source_allowlist
                regression_suite = spec.regression_suite
                pythonpath = spec.pythonpath
                timeout_seconds = spec.timeout_seconds
            else:
                case_id = task.case_id
                case = load_case(case_id)
                case_name = str(case["name"])
                selector = case_selector(case_id)
                diagnostic_queries = DIAGNOSTIC_QUERIES[case_id]
                source_allowlist = ("src/eventrelay",)
                regression_suite = "tests"
                pythonpath = ("src",)
                timeout_seconds = 30
            phase = recovery_state(checkpoint).get("phase")
            transport = (
                _DeniedResumeTransport()
                if phase in {PATCH_APPLIED, TARGET_PASSED}
                or _has_successful_tool_result(store, task_id, "apply_patch")
                else BailianChatTransport()
            )
            resume = True
        elif arguments.task:
            spec = RepositoryTaskSpec.load(arguments.task)
            issue = spec.issue
            selector = spec.target_test
            diagnostic_queries = spec.diagnostic_queries
            source_allowlist = spec.source_allowlist
            regression_suite = spec.regression_suite
            pythonpath = spec.pythonpath
            timeout_seconds = spec.timeout_seconds
            run_id = uuid4().hex[:8]
            workspace = materialize_repository(
                spec,
                ROOT / "workspaces" / "model-agent" / f"repo-{spec.name}-{run_id}",
            )
            task_id = f"model-agent-repo-{spec.name}-{run_id}"
            case_id = f"repo-{spec.name}"
            case_name = spec.name
            store.create_task(Task(task_id, case_id, issue, str(workspace)))
            checkpoint = store.load_checkpoint(task_id)
            checkpoint["repository_task"] = spec.runtime_payload()
            store.save_checkpoint(task_id, checkpoint)
            store.append_event(
                task_id,
                "run_metadata",
                {
                    "agent_version": AGENT_VERSION,
                    "project_version": PROJECT_VERSION,
                    "model": MODEL_ID,
                    "planner_protocol": PLANNER_PROTOCOL,
                    "prompt_protocol": "native-function-calling-v0.8.3-dev1",
                    "rag_mode": arguments.rag,
                    "repository_task": spec.name,
                    "target_selector": selector,
                    "regression_suite": regression_suite,
                    "source_allowlist": list(source_allowlist),
                    "diagnostic_queries": list(diagnostic_queries),
                    "max_model_calls": MAX_MODEL_CALLS,
                    "max_completion_tokens": MAX_TOTAL_COMPLETION_TOKENS,
                },
            )
            store.transition(task_id, TaskStatus.READY, "configured repository workspace created")
            store.transition(task_id, TaskStatus.RUNNING, "configured repository workflow started")
            transport = BailianChatTransport()
            resume = False
        else:
            case_id = arguments.case or "05"
            case = load_case(case_id)
            case_name = str(case["name"])
            if case["split"] != arguments.evaluation_split:
                parser.error(
                    f"case {case_id} belongs to the {case['split']} split, "
                    f"not {arguments.evaluation_split}"
                )
            issue = str(case["issue"])
            selector = case_selector(case_id)
            diagnostic_queries = DIAGNOSTIC_QUERIES[case_id]
            source_allowlist = ("src/eventrelay",)
            regression_suite = "tests"
            pythonpath = ("src",)
            timeout_seconds = 30
            run_id = uuid4().hex[:8]
            workspace = materialize_case(
                case_id,
                ROOT / "workspaces" / "model-agent" / f"case-{case_id}-{run_id}",
            )
            task_id = f"model-agent-{case_id}-{run_id}"
            store.create_task(Task(task_id, case_id, issue, str(workspace)))
            store.append_event(
                task_id,
                "run_metadata",
                {
                    "agent_version": AGENT_VERSION,
                    "project_version": PROJECT_VERSION,
                    "model": MODEL_ID,
                    "planner_protocol": PLANNER_PROTOCOL,
                    "prompt_protocol": "native-function-calling-v0.8.3-dev1",
                    "rag_mode": arguments.rag,
                    "case_name": case_name,
                    "evaluation_split": str(case["split"]),
                    "target_selector": selector,
                    "diagnostic_queries": list(diagnostic_queries),
                    "max_model_calls": MAX_MODEL_CALLS,
                    "max_completion_tokens": MAX_TOTAL_COMPLETION_TOKENS,
                },
            )
            store.transition(task_id, TaskStatus.READY, "end-to-end workspace created")
            store.transition(task_id, TaskStatus.RUNNING, "end-to-end model workflow started")
            transport = BailianChatTransport()
            resume = False

        tools = InstrumentedTools(
            task_id,
            store,
            ReadOnlyRepository(workspace, allowed_roots=source_allowlist),
            RestrictedTestRunner(
                workspace,
                allowed_targets=(selector,),
                regression_selector=regression_suite,
                pythonpath=pythonpath,
                timeout_seconds=timeout_seconds,
            ),
            PatchApplier(workspace, PatchPolicy(allowed_roots=source_allowlist)),
        )
        rag_retriever = None
        if arguments.rag != "none" and not resume:
            embedding_provider = None
            if arguments.rag == "hash":
                embedding_provider = HashEmbeddingProvider(arguments.embedding_dimensions)
            elif arguments.rag == "hybrid":
                embedding_provider = BailianEmbeddingProvider(
                    model_id=arguments.embedding_model,
                    dimensions=arguments.embedding_dimensions,
                )
            safe_case_name = re.sub(r"[^A-Za-z0-9._-]+", "-", case_name).strip("-")[:80]
            model_name = (
                embedding_provider.model_id if embedding_provider is not None else "lexical-only"
            )
            safe_model_name = re.sub(r"[^A-Za-z0-9._-]+", "-", model_name).strip("-")[:80]
            code_index = CodeIndex(
                ROOT / "data" / "retrieval" / f"{safe_case_name}-{safe_model_name}.sqlite3"
            )
            build = code_index.build(
                workspace,
                allowed_roots=source_allowlist,
                embedding_provider=embedding_provider,
            )
            rag_retriever = CodeRagRetriever(
                code_index,
                embedding_provider=embedding_provider,
                limit=arguments.rag_limit,
                rrf_k=arguments.rrf_k,
            )
            store.append_event(
                task_id,
                "rag_index_built",
                {
                    "mode": rag_retriever.mode,
                    "chunks": build.chunks,
                    "files": build.files,
                    "repository_sha256": build.repository_sha256,
                    "embedding_model": build.embedding_model,
                    "embedding_dimensions": build.embedding_dimensions,
                    "top_k": arguments.rag_limit,
                    "rrf_k": arguments.rrf_k,
                    "fusion": "file_level_reciprocal_rank_fusion",
                    "cache_contract": "exact repository and retrieval metadata match only",
                    "execution_authority": False,
                },
            )
        planner = NativeFunctionPlanner(
            transport,
            PlannerConfig(
                max_completion_tokens=MAX_COMPLETION_TOKENS,
                max_calls_per_task=MAX_MODEL_CALLS,
                max_total_completion_tokens=MAX_TOTAL_COMPLETION_TOKENS,
            ),
        )
        task_evidence = f"{issue} Failing target: {selector}."
        result = LangGraphEndToEndRepairWorkflow(
            task_id,
            store,
            planner,
            tools,
            target_selector=selector,
            allowed_source_roots=source_allowlist,
            max_diagnosis_turns=MAX_DIAGNOSIS_TURNS,
            crash_after=arguments.inject_crash_after,
            rag_retriever=rag_retriever,
        ).run(
            task_evidence,
            diagnostic_queries=diagnostic_queries,
            resume=resume,
        )
        budget = store.load_checkpoint(task_id).get("model_budget", {})
        print("End-to-end repair run completed.")
        print(f"Agent version: {AGENT_VERSION}; task: {case_id} ({case_name})")
        print(f"Diagnosis turns: {result.diagnosis_turns}/{MAX_DIAGNOSIS_TURNS}")
        print(
            f"Model usage: calls={budget.get('calls', 0)}/{MAX_MODEL_CALLS}, "
            f"output_tokens={result.completion_tokens}/{MAX_TOTAL_COMPLETION_TOKENS}"
        )
        print(f"Verification action: {result.action}")
        print(f"Final task status: {result.task_status.value}")
        print(f"Detail: {result.detail}")
        if resume:
            print("Recovery: completed tools were verified and not executed again.")
        print(f"Trace database: data/model-agent.sqlite3 (task {task_id})")
    except InjectedCrash as error:
        print(f"Injected crash recorded after durable checkpoint: {error.point}")
        print(f"Resume with: python scripts\\model_repair_agent.py --resume {task_id}")
        print(f"Trace database: data/model-agent.sqlite3 (task {task_id})")
        raise SystemExit(75) from error
    except PlannerError as error:
        if store.get_task(task_id).status is TaskStatus.RUNNING:
            store.transition(task_id, TaskStatus.NEEDS_HUMAN, f"planner stopped safely: {error}")
        print(f"End-to-end repair stopped safely: {error}")
        print(f"Trace database: data/model-agent.sqlite3 (task {task_id})")
        raise SystemExit(1) from error
    except RepositoryTaskError as error:
        if "task_id" in locals():
            try:
                if store.get_task(task_id).status is TaskStatus.RUNNING:
                    store.transition(task_id, TaskStatus.NEEDS_HUMAN, f"task config rejected: {error}")
            except KeyError:
                pass
        print(f"Configured repository task rejected safely: {error}")
        raise SystemExit(2) from error
    except RetrievalError as error:
        if "task_id" in locals():
            try:
                if store.get_task(task_id).status is TaskStatus.RUNNING:
                    store.transition(task_id, TaskStatus.NEEDS_HUMAN, f"RAG stopped safely: {error}")
            except KeyError:
                pass
        print(f"Code RAG stopped safely: {error}")
        raise SystemExit(3) from error
    finally:
        if code_index is not None:
            code_index.close()
        store.close()


class _DeniedResumeTransport:
    def complete(self, payload: dict[str, object]) -> dict[str, object]:
        raise PlannerError("model call is not permitted during verification-only resume")


def _prepare_resume(store: TraceStore, task_id: str, parser: argparse.ArgumentParser) -> Task:
    if not task_id.startswith("model-agent-") or len(task_id) > 80:
        parser.error("resume task id is outside the model-agent namespace")
    try:
        task = store.get_task(task_id)
    except KeyError:
        parser.error(f"unknown resume task: {task_id}")
    workspace = Path(task.workspace).resolve()
    allowed_root = (ROOT / "workspaces" / "model-agent").resolve()
    if not workspace.is_relative_to(allowed_root) or not workspace.is_dir():
        parser.error("resume workspace is outside the allowlisted model-agent root")
    if task.status is TaskStatus.INTERRUPTED:
        store.transition(task_id, TaskStatus.READY, "operator requested checkpoint resume")
        store.transition(task_id, TaskStatus.RUNNING, "checkpoint resume started")
    elif task.status is not TaskStatus.RUNNING:
        parser.error(f"task status {task.status.value} cannot be resumed")
    store.append_event(
        task_id,
        "resume_requested",
        {"previous_status": task.status.value},
    )
    return store.get_task(task_id)


def _has_successful_tool_result(store: TraceStore, task_id: str, tool: str) -> bool:
    return any(
        event.event_type == "tool_finished"
        and event.payload.get("tool") == tool
        and event.payload.get("ok") is True
        for event in store.list_events(task_id)
    )


if __name__ == "__main__":
    main()
