from __future__ import annotations

import asyncio
import uuid

from . import skill_logic as S
from .evidence import EvidenceStore
from .markdown import decision_request, diagnosis, investigation_started, postmortem, resolved
from .models import *
from .monitoring import MONITORING_MARKER, MonitoringIssueRegistry, log_event
from .policy import PolicyEngine
from .store import RunStore


class Orchestrator:
    def __init__(self, cfg: dict, github, openclaw, data_dir="runtime-data"):
        self.cfg = cfg
        self.github = github
        self.oc = openclaw
        self.store = RunStore(data_dir)
        self.issue_registry = MonitoringIssueRegistry(data_dir)
        self.ev = EvidenceStore(data_dir)
        self.policy = PolicyEngine(cfg)
        self.runs = {r.issue_number: r for r in self.store.load_all()}
        self._locks: dict[int, asyncio.Lock] = {}

    def profile(self, name: str) -> str:
        return self.cfg["openclaw"]["profiles"][name]

    def _identity(self, run: RunRecord) -> dict:
        incident = run.incident
        return {
            "run_id": run.run_id,
            "issue_number": run.issue_number,
            "incident_id": incident.incident_id if incident else None,
            "incidentlab_run_id": incident.incidentlab_run_id if incident else None,
            "scenario_id": incident.scenario_id if incident else None,
        }

    def _log(self, run: RunRecord, event: str, **extra) -> None:
        log_event(event, **self._identity(run), **extra)

    async def _save(self, run, kind, payload):
        self.ev.append(run.run_id, kind, payload)
        self.store.save(run)

    async def _set_state(self, run: RunRecord, state: RunState):
        run.transition(state)
        self.store.save(run)
        self._log(run, "RUN_STATE_CHANGED", state=state.value)
        cfg = self.cfg.get("labels", {})
        current = (cfg.get("lifecycle") or {}).get(state.value)
        base = cfg.get("base", ["opsswarm", "incident"])
        labels = base + ([current] if current else [])
        if run.incident and run.incident.severity.startswith("SEV"):
            labels.append("sev:" + run.incident.severity[3:])
        try:
            await self.github.replace_labels(run.issue_number, labels)
        except Exception as exc:
            # Labels are metadata, never a workflow authority or availability gate.
            self._log(
                run,
                "ISSUE_LABEL_WARNING",
                state=state.value,
                labels=labels,
                error_type=type(exc).__name__,
                error=str(exc),
            )

    async def start_issue(self, number: int) -> RunRecord:
        lock = self._locks.setdefault(number, asyncio.Lock())
        async with lock:
            existing = self.runs.get(number)
            if existing and existing.state not in {RunState.FAILED, RunState.ABORTED}:
                self._log(existing, "ORCHESTRATION_DEDUPLICATED", state=existing.state.value)
                return existing

            run = None
            try:
                issue = await self.github.get_issue(number)
                req = self.cfg.get("required_issue_label", "opsswarm")
                names = [x.get("name", "") for x in issue.get("labels", []) if isinstance(x, dict)]
                trusted_monitoring = MONITORING_MARKER in (issue.get("body") or "")
                if req and req not in names and not trusted_monitoring:
                    raise RuntimeError(f"Issue #{number} lacks required label {req} and is not a trusted monitoring Issue")
                if req and req not in names and trusted_monitoring:
                    log_event("ISSUE_LABEL_WARNING", issue_number=number, required_label=req, reason="trusted_monitoring_marker_allows_orchestration")

                run = RunRecord(run_id=f"RUN-GH-{number}-{uuid.uuid4().hex[:8]}", issue_number=number)
                self.runs[number] = run
                await self._save(run, "S8.orchestration_entry", {"issue_number": number, "source": "github"})
                await self._set_state(run, RunState.TRIAGE)

                run.incident = S.parse_issue(number, issue)
                await self._save(run, "S1.incident", run.incident.model_dump())
                self._log(run, "S1_COMPLETED", service=run.incident.service, severity=run.incident.severity)
                await self._investigate(run)
                return run
            except Exception as exc:
                if run:
                    run.error = f"{type(exc).__name__}: {exc}"
                    try:
                        await self._set_state(run, RunState.FAILED)
                    except Exception:
                        run.transition(RunState.FAILED)
                        self.store.save(run)
                    self.ev.append(run.run_id, "runtime.error", {"type": type(exc).__name__, "message": str(exc)})
                    self._log(run, "ORCHESTRATION_BLOCKED", error_type=type(exc).__name__, error=str(exc))
                    try:
                        await self.github.comment(
                            number,
                            f"## OpsSwarm — Orchestration blocked\n\n`{type(exc).__name__}: {exc}`\n\nThe Issue remains open. No recovery was authorized by this failure.",
                        )
                    except Exception as comment_exc:
                        self._log(run, "GITHUB_COMMENT_WARNING", error_type=type(comment_exc).__name__, error=str(comment_exc))
                raise

    async def _investigate(self, run: RunRecord, extra_task: Task | None = None):
        await self._set_state(run, RunState.INVESTIGATING)
        main = self.profile("incident-manager")
        if extra_task:
            run.tasks.append(extra_task)
        elif not run.tasks:
            run.tasks = await S.build_tasks(self.oc, main, run.run_id, run.incident)
            if not run.tasks:
                raise RuntimeError("S2 produced no investigation tasks")
            await self.github.comment(run.issue_number, investigation_started(run))
            await self._save(run, "S2.task_graph", {"tasks": [t.model_dump() for t in run.tasks]})
            self._log(run, "S2_COMPLETED", task_count=len(run.tasks))

        done = {f.task_id for f in run.findings}
        pending = [t for t in run.tasks if t.id not in done]
        while pending:
            ready = [t for t in pending if all(dep in done for dep in t.depends_on)]
            if not ready:
                raise RuntimeError("Task graph has unsatisfied/cyclic dependencies")

            async def one(t):
                agent = self.profile(t.profile)
                t.status = "RUNNING"
                self.store.save(run)
                self._log(run, "S4_AGENT_STARTED", task_id=t.id, agent=agent, risk=t.risk.value)
                try:
                    finding = await S.execute_task(self.oc, agent, run.run_id, run.incident, t)
                    t.status = "DONE"
                    self._log(run, "S4_AGENT_COMPLETED", task_id=t.id, agent=agent)
                    return finding
                except Exception as exc:
                    t.status = "FAILED"
                    self.store.save(run)
                    self._log(run, "S4_AGENT_FAILED", task_id=t.id, agent=agent, error_type=type(exc).__name__, error=str(exc))
                    raise

            results = await asyncio.gather(*(one(t) for t in ready))
            for finding in results:
                run.findings.append(finding)
                done.add(finding.task_id)
                await self._save(run, "S4.finding", finding.model_dump())
            pending = [t for t in pending if t.id not in done]

        aggregation = {
            "finding_count": len(run.findings),
            "task_ids": [f.task_id for f in run.findings],
            "status": "COMPLETED",
        }
        await self._save(run, "S5.evidence_aggregation", aggregation)
        self._log(run, "S5_COMPLETED", finding_count=len(run.findings))

        run.root_cause = await S.synthesize_root_cause(self.oc, main, run.run_id, run.incident, run.findings, run.human_inputs)
        await self._set_state(run, RunState.DIAGNOSED)
        await self._save(run, "RCA.root_cause", run.root_cause.model_dump())
        self._log(run, "RCA_COMPLETED", confidence=run.root_cause.confidence, rca_status=run.root_cause.status)
        await self.github.comment(run.issue_number, diagnosis(run))
        rca_threshold = float(self.cfg.get("root_cause_confidence_threshold", 0.80))
        if run.root_cause.status == "uncertain" or run.root_cause.confidence < rca_threshold:
            question = run.root_cause.human_input_question or "Root-cause confidence is below the autonomous threshold. Provide relevant operational/business context, or use `/opsswarm investigate <request>` to request more read-only evidence."
            run.decision = DecisionRequest(
                id=f"DEC-{run.issue_number}-{uuid.uuid4().hex[:6]}",
                kind="INPUT",
                reason="Root-cause analysis is not sufficiently certain for autonomous remediation",
                question=question,
            )
            await self._set_state(run, RunState.WAITING_INPUT)
            await self._save(run, "Policy.human_gate", run.decision.model_dump())
            await self.github.comment(run.issue_number, decision_request(run))
            return
        await self._plan(run)

    async def _plan(self, run: RunRecord):
        await self._set_state(run, RunState.PLANNING)
        main = self.profile("incident-manager")
        run.recovery_plan = await S.make_recovery_plan(self.oc, main, run.run_id, run.incident, run.root_cause, run.human_inputs)
        await self._save(run, "S3.recovery_plan", run.recovery_plan.model_dump())
        self._log(run, "S3_COMPLETED", option_count=len(run.recovery_plan.options))
        action, reason = self.policy.classify_plan(run.recovery_plan)
        self._log(run, "POLICY_DECISION", decision=action, reason=reason)
        await self._save(run, "Policy.decision", {"decision": action, "reason": reason})
        if action == "AUTO":
            option = run.recovery_plan.options[0]
            await self._execute_option(run, option)
            return
        if action in {"APPROVAL", "DECISION", "INPUT"}:
            kind = {"APPROVAL": "APPROVAL", "DECISION": "DECISION", "INPUT": "INPUT"}[action]
            run.decision = DecisionRequest(
                id=f"DEC-{run.issue_number}-{uuid.uuid4().hex[:6]}",
                kind=kind,
                reason=reason,
                options=run.recovery_plan.options if action != "INPUT" else [],
                recommended_option=run.recovery_plan.recommended_option,
                question=run.recovery_plan.business_input_question,
            )
            await self._set_state(
                run,
                {"APPROVAL": RunState.WAITING_APPROVAL, "DECISION": RunState.WAITING_DECISION, "INPUT": RunState.WAITING_INPUT}[action],
            )
            await self._save(run, "Policy.human_gate", run.decision.model_dump())
            await self.github.comment(run.issue_number, decision_request(run))
            return
        run.error = reason
        await self._set_state(run, RunState.FAILED)
        await self.github.comment(run.issue_number, f"## OpsSwarm — Policy denied\n\n{reason}\n\nIssue remains open.")

    async def _execute_option(self, run: RunRecord, option: RemediationOption):
        await self._set_state(run, RunState.EXECUTING)
        self._log(run, "RECOVERY_STARTED", option_id=option.id, risk=option.risk.value)
        run.execution = await S.execute_recovery(
            self.oc,
            self.profile("recovery-responder"),
            run.run_id,
            run.incident,
            run.root_cause,
            option,
        )
        await self._save(run, "Recovery.execution", run.execution.model_dump())
        self._log(run, "RECOVERY_COMPLETED", option_id=option.id, success=run.execution.success, ambiguous=run.execution.ambiguous)
        if run.execution.ambiguous:
            await self._save(run, "S6.reconciliation_required", {"reason": "ambiguous_write", "option_id": option.id})
            self._log(run, "S6_RECONCILIATION_REQUIRED", option_id=option.id)
            run.decision = DecisionRequest(
                id=f"DEC-{run.issue_number}-{uuid.uuid4().hex[:6]}",
                kind="DECISION",
                reason="The write outcome is ambiguous. Blind retry is prohibited.",
                options=[],
                question="Use /opsswarm investigate <read-only verification request>, /opsswarm abort, or /opsswarm resume after external confirmation.",
            )
            await self._set_state(run, RunState.WAITING_DECISION)
            await self.github.comment(run.issue_number, decision_request(run))
            return
        await self._save(run, "S6.reconciliation", {"required": False, "reason": "execution_unambiguous"})
        self._log(run, "S6_NOT_REQUIRED", reason="execution_unambiguous")
        if not run.execution.success:
            run.error = run.execution.summary
            await self._set_state(run, RunState.FAILED)
            await self.github.comment(run.issue_number, f"## OpsSwarm — Recovery failed\n\n{run.execution.summary}\n\nIssue remains open.")
            return
        await self._verify(run)

    async def _verify(self, run: RunRecord):
        await self._set_state(run, RunState.VERIFYING)
        self._log(run, "S7_STARTED")
        run.verification = await S.verify_recovery(
            self.oc,
            self.profile("observability-investigator"),
            run.run_id,
            run.incident,
            run.execution,
        )
        await self._save(run, "S7.verification", run.verification.model_dump())
        threshold = float(self.cfg.get("verification_confidence_threshold", 0.85))
        if not run.verification.verified or run.verification.confidence < threshold:
            run.error = "Independent recovery verification failed or confidence below threshold"
            await self._set_state(run, RunState.FAILED)
            self._log(run, "S7_FAILED", confidence=run.verification.confidence, verified=run.verification.verified)
            await self.github.comment(run.issue_number, f"## OpsSwarm — Verification failed\n\n{run.verification.summary}\n\nIssue remains open.")
            return
        self._log(run, "S7_PASSED", confidence=run.verification.confidence)
        await self._set_state(run, RunState.RESOLVED)
        await self.github.comment(run.issue_number, resolved(run))
        await self.github.comment(run.issue_number, postmortem(run))
        # Corrective actions belong to the parent incident record. Creating one GitHub
        # Issue per RCA action causes issue explosion and breaks incident-to-issue cardinality.
        if run.root_cause and run.root_cause.corrective_actions:
            actions = list(dict.fromkeys(a.strip() for a in run.root_cause.corrective_actions if a and a.strip()))
            if actions:
                checklist = "\n".join(f"- [ ] {action}" for action in actions)
                await self.github.comment(
                    run.issue_number,
                    "## OpsSwarm - Corrective actions\n\n"
                    "These actions are tracked under the parent incident; no child Issue is created.\n\n"
                    + checklist,
                )
                await self._save(run, "RCA.corrective_actions", {"count": len(actions), "actions": actions, "tracking": "parent_issue"})
                self._log(run, "CORRECTIVE_ACTIONS_ATTACHED", count=len(actions), tracking="parent_issue")
        await self.github.close_issue(run.issue_number)
        self.issue_registry.mark_status(run.issue_number, "RESOLVED")
        self._log(run, "ISSUE_CLOSED_AFTER_S7")

    async def handle_comment(self, number: int, actor: str, body: str, permission: str, command):
        run = self.runs.get(number)
        if not run:
            return
        if not command:
            run.human_inputs.append({"actor": actor, "text": body, "authority": "information-only"})
            await self._save(run, "human.free_text", run.human_inputs[-1])
            return
        rank = {"none": 0, "read": 1, "triage": 2, "write": 3, "maintain": 4, "admin": 5}
        min_input = self.cfg.get("human_authority", {}).get("minimum_permission_for_input", "read")
        min_approval = self.cfg.get("human_authority", {}).get("minimum_permission_for_approval", "maintain")
        min_abort = self.cfg.get("human_authority", {}).get("minimum_permission_for_abort", "maintain")

        def require(level):
            if rank.get(permission, 0) < rank.get(level, 99):
                raise PermissionError(f"@{actor} has {permission}; requires {level}")

        if command.name in {"provide", "investigate", "resume"}:
            require(min_input)
        elif command.name in {"approve", "reject"}:
            require(min_approval)
        elif command.name == "abort":
            require(min_abort)

        self._log(run, "GITHUB_COMMAND_ACCEPTED", actor=actor, command=command.name, permission=permission)
        if command.name == "abort":
            run.error = f"Aborted by @{actor}"
            await self._set_state(run, RunState.ABORTED)
            await self.github.comment(number, f"## OpsSwarm — Aborted\n\nBy `@{actor}`.")
            return
        if command.name == "provide":
            run.human_inputs.append({"actor": actor, "text": command.argument, "authority": "provided-input"})
            run.decision = None
            await self._save(run, "human.input", run.human_inputs[-1])
            await self._investigate(run)
            return
        if command.name == "investigate":
            extra = await S.make_extra_task(self.oc, self.profile("incident-manager"), run.run_id, run.incident, command.argument)
            extra.id = f"HX{len([t for t in run.tasks if t.id.startswith('HX')]) + 1}"
            run.decision = None
            await self._investigate(run, extra_task=extra)
            return
        if command.name == "reject":
            if run.decision:
                run.decision.status = "REJECTED"
            run.error = f"Proposed remediation rejected by @{actor}"
            await self._set_state(run, RunState.WAITING_DECISION)
            await self.github.comment(number, "OpsSwarm recorded the rejection. Use `/opsswarm investigate ...`, `/opsswarm provide ...`, or `/opsswarm abort`.")
            return
        if command.name == "approve":
            if not run.recovery_plan:
                raise RuntimeError("No recovery plan exists")
            option = next((o for o in run.recovery_plan.options if o.id == command.argument), None)
            if not option:
                raise ValueError(f"Unknown option id: {command.argument}")
            if self.policy.action(option.risk) == "DENY":
                raise PermissionError("Policy denies this option regardless of human approval")
            if run.decision:
                run.decision.status = "ANSWERED"
            await self._save(run, "human.approval", {"actor": actor, "option": option.id, "permission": permission})
            await self._execute_option(run, option)
            return
        if command.name == "resume":
            if run.state == RunState.FAILED and run.execution and run.execution.success:
                await self._verify(run)
            else:
                await self.github.comment(number, "`/opsswarm resume` is only accepted when a safe checkpoint exists. Use an explicit approve/investigate/provide command.")
